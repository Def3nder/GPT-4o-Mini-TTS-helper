"""Thin command-line interface for project diagnostics."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
import re
import sys

from markdown_tts.audio import (
    AudioProcessingError,
    AudioJoinError,
    AudioOutputExistsError,
    UnsupportedAudioJoinerError,
    UnsupportedAudioEncoderError,
    WavAudioJoiner,
    WavPrefillTrimmer,
    create_audio_encoder,
    create_audio_joiner,
)
from markdown_tts.application import (
    ChunkBatchConfigurationError,
    ChunkBatchGenerationError,
    ChunkedMarkdownMergedAudioConverter,
    ChunkedMarkdownAudioConverter,
    ChunkOutputExistsError,
    MarkdownAudioConverter,
    PrefillCalibrator,
    PrefillMarkdownAudioConverter,
    PrefillPipelineConfigurationError,
    SpeechInputLimitError,
)
from markdown_tts.chunker import SemanticChunker, SpeechChunk, UnchunkableSpeechError
from markdown_tts.config import (
    AudioEncoderConfig,
    AudioJoinerConfig,
    ChunkingRules,
    ConfigurationError,
    ParserRules,
    PrefillConfig,
    SemanticRendererRules,
    TTSProviderConfig,
)
from markdown_tts.loader import MarkdownLoadError, load_markdown
from markdown_tts.parser import MarkdownParser
from markdown_tts.prefill import (
    PrefillCalibrationError,
    prefill_calibration_audio_path,
)
from markdown_tts.profiles import SpeechProfileCatalog
from markdown_tts.progress import SynthesisProgress
from markdown_tts.semantic_renderer import SemanticRenderer, SpeechDocument
from markdown_tts.speech_renderer import EmptySpeechDocumentError, SpeechRenderer
from markdown_tts.tts import (
    MissingApiKeyError,
    OutputFileExistsError,
    TTSGenerationError,
    UnsupportedTTSProviderError,
    create_tts_provider,
)
from markdown_tts.usage import SpeechUsageAccumulator, calculate_speech_cost


def _build_argument_parser() -> argparse.ArgumentParser:
    help_formatter = argparse.RawDescriptionHelpFormatter
    parser = argparse.ArgumentParser(
        prog="markdown-tts",
        formatter_class=help_formatter,
        description="Markdown-Dokumente für die Sprachsynthese aufbereiten und vertonen.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    runtime_options = argparse.ArgumentParser(add_help=False)
    runtime_options.add_argument(
        "--log-level",
        choices=("DEBUG", "INFO", "WARNING", "ERROR"),
        default="INFO",
        help="Detailgrad des Laufzeit-Loggings",
    )
    runtime_options.add_argument(
        "--log-file",
        type=Path,
        help="Optionaler Pfad für ein zusätzliches UTF-8-Logfile",
    )
    automatic = commands.add_parser(
        "auto",
        prog="markdown-tts",
        help="Syntheseweg anhand der Länge automatisch auswählen",
        parents=[runtime_options],
        formatter_class=help_formatter,
        description=(
            "Kurze Texte direkt als MP3 und lange Texte automatisch über den "
            "Prefill-Qualitätsmodus erzeugen."
        ),
    )
    automatic.add_argument(
        "input",
        type=Path,
        metavar="INPUT",
        help="[Pflicht] Pfad zur Markdown-Datei",
    )
    automatic.add_argument(
        "output",
        type=Path,
        nargs="?",
        metavar="OUTPUT",
        help="[Optional] Fertige MP3; Standard: INPUT mit der Endung .mp3",
    )
    automatic.add_argument(
        "--parser-config",
        type=Path,
        default=Path("config/parser_rules.json"),
    )
    automatic.add_argument(
        "--renderer-config",
        type=Path,
        default=Path("config/semantic_renderer.json"),
    )
    automatic.add_argument(
        "--chunking-config",
        type=Path,
        default=Path("config/chunking.json"),
    )
    automatic.add_argument(
        "--provider-config",
        type=Path,
        default=Path("config/tts_provider.json"),
        help="Provider-Konfiguration für kurze direkte MP3-Aufrufe",
    )
    automatic.add_argument(
        "--prefill-provider-config",
        type=Path,
        default=Path("config/tts_provider_wav.json"),
        help="WAV-Provider-Konfiguration für automatisch gewählte Prefill-Aufrufe",
    )
    automatic.add_argument(
        "--prefill-config",
        type=Path,
        default=Path("config/prefill.json"),
    )
    automatic.add_argument(
        "--encoder-config",
        type=Path,
        default=Path("config/audio_encoder.json"),
    )
    automatic.add_argument(
        "--calibration",
        type=Path,
        help="Optionale explizite Prefill-Kalibrierungsdatei für Experten",
    )
    automatic.add_argument(
        "--calibration-cache-dir",
        type=Path,
        default=Path("output/prefill-calibrations"),
    )
    automatic.add_argument(
        "--refresh-calibration",
        action="store_true",
        help="Eine automatisch benötigte Prefill-Kalibrierung neu erzeugen",
    )
    automatic.add_argument(
        "--profile",
        default="coaching",
        help="[Optional] Profilname oder JSON-Pfad; Standard: coaching",
    )
    automatic.add_argument(
        "--append-profile-name",
        action="store_true",
        help="Verwendeten Profilnamen an den Ausgabestamm anhängen",
    )
    automatic.add_argument(
        "--profiles-dir",
        type=Path,
        default=Path("speech_profiles"),
    )
    automatic.add_argument(
        "--overwrite",
        action="store_true",
        help="Eine vorhandene finale MP3 ausdrücklich ersetzen",
    )
    automatic.add_argument(
        "--keep-chunks",
        action="store_true",
        help="Bei automatisch gewähltem Prefill-Modus WAV-Artefakte behalten",
    )
    automatic.add_argument(
        "--no-progress",
        action="store_true",
        help="Formatierte Fortschritts- und Usage-Ausgabe unterdrücken",
    )
    profiles = commands.add_parser(
        "profiles",
        help="Verfügbare Sprachprofile auflisten oder ein Profil anzeigen",
        parents=[runtime_options],
    )
    profiles.add_argument(
        "name",
        nargs="?",
        help="Optionaler Profilname für die Detailansicht",
    )
    profiles.add_argument(
        "--profiles-dir",
        type=Path,
        default=Path("speech_profiles"),
        help="Verzeichnis mit JSON-Sprachprofilen",
    )
    preview = commands.add_parser(
        "preview",
        help="Sprechbaren Text und Semantik anzeigen",
        parents=[runtime_options],
    )
    preview.add_argument("input", type=Path, help="Pfad zur Markdown-Datei")
    preview.add_argument(
        "--parser-config",
        type=Path,
        default=Path("config/parser_rules.json"),
    )
    preview.add_argument(
        "--renderer-config",
        type=Path,
        default=Path("config/semantic_renderer.json"),
    )
    preview.add_argument(
        "--show-cues",
        action="store_true",
        help="Markdown-Hervorhebungen mit Textpositionen anzeigen",
    )
    preview.add_argument(
        "--chunking-config",
        type=Path,
        default=Path("config/chunking.json"),
    )
    preview.add_argument(
        "--show-chunks",
        action="store_true",
        help="Geplante TTS-Chunks mit Größe und Grenzen anzeigen",
    )
    preview.add_argument(
        "--prefill",
        action="store_true",
        help="Bei der Chunk-Vorschau Platz für den konfigurierten Vorspann reservieren",
    )
    preview.add_argument(
        "--prefill-config",
        type=Path,
        default=Path("config/prefill.json"),
    )
    synthesize = commands.add_parser(
        "synthesize",
        help="Kurzes Markdown-Dokument als einzelne Audiodatei erzeugen",
        parents=[runtime_options],
        formatter_class=help_formatter,
        description="Ein kurzes Markdown-Dokument als einzelne MP3 erzeugen.",
        epilog=(
            "Vollständiger Aufruf:\n"
            "  markdown-tts synthesize INPUT [OUTPUT] [OPTIONEN]\n\n"
            "INPUT ist verpflichtend. OUTPUT und alle mit '--' beginnenden Parameter "
            "sind optional. Ohne OUTPUT wird neben INPUT eine gleichnamige .mp3-Datei "
            "erzeugt. Ohne --profile wird das Standardprofil 'coaching' verwendet."
        ),
    )
    synthesize.add_argument(
        "input",
        type=Path,
        metavar="INPUT",
        help="[Pflicht] Pfad zur Markdown-Datei",
    )
    synthesize.add_argument(
        "output",
        type=Path,
        nargs="?",
        metavar="OUTPUT",
        help="[Optional] Ausgabedatei; Standard: INPUT mit der Endung .mp3",
    )
    synthesize.add_argument(
        "--parser-config",
        type=Path,
        default=Path("config/parser_rules.json"),
    )
    synthesize.add_argument(
        "--renderer-config",
        type=Path,
        default=Path("config/semantic_renderer.json"),
    )
    synthesize.add_argument(
        "--provider-config",
        type=Path,
        default=Path("config/tts_provider.json"),
    )
    synthesize.add_argument(
        "--chunking-config",
        type=Path,
        default=Path("config/chunking.json"),
        help="Konfiguration des vor dem API-Aufruf geprüften Zeichenlimits",
    )
    synthesize.add_argument(
        "--profile",
        default="coaching",
        help=(
            "[Optional] Profilname oder Pfad zu einer JSON-Profildatei; "
            "Standard: coaching"
        ),
    )
    synthesize.add_argument(
        "--append-profile-name",
        action="store_true",
        help=(
            "[Optional] Verwendeten Profilnamen an den Ausgabestamm anhängen, "
            "z. B. text_coaching.mp3"
        ),
    )
    synthesize.add_argument(
        "--profiles-dir",
        type=Path,
        default=Path("speech_profiles"),
        help="Verzeichnis für die Auswahl per Profilname",
    )
    synthesize.add_argument(
        "--overwrite",
        action="store_true",
        help="Eine vorhandene Ausgabedatei ausdrücklich ersetzen",
    )
    synthesize.add_argument(
        "--no-progress",
        action="store_true",
        help="Formatierte Fortschritts- und Usage-Ausgabe unterdrücken",
    )
    synthesize_chunks = commands.add_parser(
        "synthesize-chunks",
        help="Langes Markdown-Dokument über MP3-Chunks als fertige MP3 erzeugen",
        parents=[runtime_options],
        formatter_class=help_formatter,
        description="Ein langes Markdown-Dokument in Chunks aufteilen und als MP3 zusammenführen.",
        epilog=(
            "Vollständiger Aufruf:\n"
            "  markdown-tts synthesize-chunks INPUT [OUTPUT] [OPTIONEN]\n\n"
            "INPUT ist verpflichtend. OUTPUT und alle mit '--' beginnenden Parameter "
            "sind optional. Ohne OUTPUT wird neben INPUT eine gleichnamige .mp3-Datei "
            "erzeugt. Die Chunks liegen vorübergehend im gleichnamigen Verzeichnis "
            "ohne .mp3-Endung. Bei einem Fehler oder mit --keep-chunks bleibt es erhalten."
        ),
    )
    synthesize_chunks.add_argument(
        "input",
        type=Path,
        metavar="INPUT",
        help="[Pflicht] Pfad zur Markdown-Datei",
    )
    synthesize_chunks.add_argument(
        "output",
        type=Path,
        nargs="?",
        metavar="OUTPUT",
        help="[Optional] Fertige MP3; Standard: INPUT mit der Endung .mp3",
    )
    synthesize_chunks.add_argument(
        "--parser-config",
        type=Path,
        default=Path("config/parser_rules.json"),
    )
    synthesize_chunks.add_argument(
        "--renderer-config",
        type=Path,
        default=Path("config/semantic_renderer.json"),
    )
    synthesize_chunks.add_argument(
        "--chunking-config",
        type=Path,
        default=Path("config/chunking.json"),
    )
    synthesize_chunks.add_argument(
        "--provider-config",
        type=Path,
        default=Path("config/tts_provider.json"),
    )
    synthesize_chunks.add_argument(
        "--profile",
        default="coaching",
        help=(
            "[Optional] Profilname oder Pfad zu einer JSON-Profildatei; "
            "Standard: coaching"
        ),
    )
    synthesize_chunks.add_argument(
        "--append-profile-name",
        action="store_true",
        help=(
            "[Optional] Verwendeten Profilnamen an den Ausgabestamm anhängen, "
            "z. B. text_coaching.mp3"
        ),
    )
    synthesize_chunks.add_argument(
        "--profiles-dir",
        type=Path,
        default=Path("speech_profiles"),
        help="Verzeichnis für die Auswahl per Profilname",
    )
    synthesize_chunks.add_argument(
        "--overwrite",
        action="store_true",
        help="Eine vorhandene finale MP3 und vorhandene Chunks ausdrücklich ersetzen",
    )
    synthesize_chunks.add_argument(
        "--keep-chunks",
        action="store_true",
        help="Temporäres Verzeichnis mit den nummerierten MP3-Chunks behalten",
    )
    synthesize_chunks.add_argument(
        "--joiner-config",
        type=Path,
        default=Path("config/audio_joiner.json"),
        help="Konfiguration für das Zusammenfügen der MP3-Chunks",
    )
    synthesize_chunks.add_argument(
        "--no-progress",
        action="store_true",
        help="Formatierte Fortschritts- und Usage-Ausgabe unterdrücken",
    )
    calibrate_prefill = commands.add_parser(
        "calibrate-prefill",
        help="Vorspannsatz einmal als WAV synthetisieren und seine Dauer kalibrieren",
        parents=[runtime_options],
    )
    calibrate_prefill.add_argument(
        "output",
        type=Path,
        help="Zielpfad der Kalibrierungsdatei im JSON-Format",
    )
    calibrate_prefill.add_argument(
        "--provider-config",
        type=Path,
        default=Path("config/tts_provider_wav.json"),
    )
    calibrate_prefill.add_argument(
        "--prefill-config",
        type=Path,
        default=Path("config/prefill.json"),
    )
    calibrate_prefill.add_argument(
        "--profile",
        default="coaching",
        help="Profilname oder Pfad zu einer JSON-Profildatei",
    )
    calibrate_prefill.add_argument(
        "--profiles-dir",
        type=Path,
        default=Path("speech_profiles"),
    )
    calibrate_prefill.add_argument(
        "--overwrite",
        action="store_true",
        help="Eine vorhandene Kalibrierungsdatei ausdrücklich ersetzen",
    )
    calibrate_prefill.add_argument(
        "--no-progress",
        action="store_true",
        help="Formatierte Fortschritts- und Usage-Ausgabe unterdrücken",
    )
    synthesize_prefill = commands.add_parser(
        "synthesize-prefill",
        help="Markdown mit WAV-Prefill-Trimming als fertige MP3 erzeugen",
        parents=[runtime_options],
        formatter_class=help_formatter,
        description="Markdown über den WAV-Prefill-Qualitätsmodus als fertige MP3 erzeugen.",
        epilog=(
            "Vollständiger Aufruf:\n"
            "  markdown-tts synthesize-prefill INPUT [OUTPUT] [OPTIONEN]\n\n"
            "INPUT ist verpflichtend. OUTPUT und alle mit '--' beginnenden Parameter "
            "sind optional. Ohne OUTPUT wird neben INPUT eine gleichnamige .mp3-Datei "
            "erzeugt. Ohne --profile wird das Standardprofil 'coaching' verwendet."
        ),
    )
    synthesize_prefill.add_argument(
        "input",
        type=Path,
        metavar="INPUT",
        help="[Pflicht] Pfad zur Markdown-Datei",
    )
    synthesize_prefill.add_argument(
        "output",
        type=Path,
        nargs="?",
        metavar="OUTPUT",
        help="[Optional] Fertige MP3; Standard: INPUT mit der Endung .mp3",
    )
    synthesize_prefill.add_argument(
        "--calibration",
        type=Path,
        help="Optionale explizite Kalibrierungsdatei für Experten",
    )
    synthesize_prefill.add_argument(
        "--calibration-cache-dir",
        type=Path,
        default=Path("output/prefill-calibrations"),
        help="Verzeichnis für automatisch verwaltete Kalibrierungen",
    )
    synthesize_prefill.add_argument(
        "--refresh-calibration",
        action="store_true",
        help="Passende Kalibrierung vor der Synthese neu erzeugen",
    )
    synthesize_prefill.add_argument(
        "--parser-config",
        type=Path,
        default=Path("config/parser_rules.json"),
    )
    synthesize_prefill.add_argument(
        "--renderer-config",
        type=Path,
        default=Path("config/semantic_renderer.json"),
    )
    synthesize_prefill.add_argument(
        "--chunking-config",
        type=Path,
        default=Path("config/chunking.json"),
    )
    synthesize_prefill.add_argument(
        "--provider-config",
        type=Path,
        default=Path("config/tts_provider_wav.json"),
    )
    synthesize_prefill.add_argument(
        "--prefill-config",
        type=Path,
        default=Path("config/prefill.json"),
    )
    synthesize_prefill.add_argument(
        "--encoder-config",
        type=Path,
        default=Path("config/audio_encoder.json"),
    )
    synthesize_prefill.add_argument(
        "--profile",
        default="coaching",
        help=(
            "[Optional] Profilname oder Pfad zu einer JSON-Profildatei; "
            "Standard: coaching"
        ),
    )
    synthesize_prefill.add_argument(
        "--append-profile-name",
        action="store_true",
        help=(
            "[Optional] Verwendeten Profilnamen an den Ausgabestamm anhängen, "
            "z. B. text_coaching.mp3"
        ),
    )
    synthesize_prefill.add_argument(
        "--profiles-dir",
        type=Path,
        default=Path("speech_profiles"),
    )
    synthesize_prefill.add_argument(
        "--overwrite",
        action="store_true",
        help="Eine vorhandene finale MP3 ausdrücklich ersetzen",
    )
    synthesize_prefill.add_argument(
        "--keep-chunks",
        action="store_true",
        help=(
            "Roh-WAVs, Prefill-bereinigte WAV-Chunks und combined.wav "
            "nach erfolgreicher Synthese behalten"
        ),
    )
    synthesize_prefill.add_argument(
        "--no-progress",
        action="store_true",
        help="Formatierte Fortschritts- und Usage-Ausgabe unterdrücken",
    )
    merge = commands.add_parser(
        "merge",
        help="Kompatible Audiodateien ohne Re-Encoding zusammenfügen",
        parents=[runtime_options],
    )
    merge.add_argument("output", type=Path, help="Pfad zur zusammengeführten Audiodatei")
    merge.add_argument(
        "inputs",
        type=Path,
        nargs="+",
        help="Geordnete Eingabedateien, mindestens zwei",
    )
    merge.add_argument(
        "--joiner-config",
        type=Path,
        default=Path("config/audio_joiner.json"),
    )
    merge.add_argument(
        "--overwrite",
        action="store_true",
        help="Eine vorhandene Ausgabedatei ausdrücklich ersetzen",
    )
    parser.epilog = _build_complete_command_overview(commands.choices)
    return parser


def _build_complete_command_overview(
    command_parsers: dict[str, argparse.ArgumentParser],
) -> str:
    """Render global help directly from every registered subcommand option."""
    sections = ["VOLLSTÄNDIGE AUFRUFE MIT ALLEN OPTIONEN"]
    for command_name, command_parser in command_parsers.items():
        usage = command_parser.format_usage().strip().removeprefix("usage: ")
        section_name = command_name
        if command_name == "auto":
            usage = usage.replace("markdown-tts auto", "markdown-tts", 1)
            section_name = "ohne Befehl (automatisch)"
        indented_usage = usage.replace("\n", "\n  ")
        option_names = [
            ", ".join(action.option_strings)
            for action in command_parser._actions
            if action.option_strings
        ]
        explicit_options = "\n".join(f"    {names}" for names in option_names)
        sections.append(
            f"\n{section_name}:\n  {indented_usage}\n  Verfügbare Optionen:\n"
            f"{explicit_options}"
        )
    sections.append(
        "\nSchreibweise: Angaben ohne eckige Klammern sind Pflicht. Angaben in "
        "eckigen Klammern sind optional. Beschreibungen und Standardwerte zeigt "
        "'markdown-tts BEFEHL -h'."
    )
    return "\n".join(sections)


def _normalize_cli_arguments(
    arguments: list[str],
    command_names: set[str],
) -> list[str]:
    """Insert the internal automatic command when the invocation starts with INPUT."""
    if not arguments or arguments[0] in command_names or arguments[0] in {"-h", "--help"}:
        return arguments
    if arguments[0].startswith("-"):
        return arguments
    return ["auto", *arguments]


def _select_automatic_synthesis_command(
    character_count: int,
    max_characters: int,
) -> str:
    """Choose the direct path at the limit and prefill only above it."""
    if character_count <= max_characters:
        return "synthesize"
    return "synthesize-prefill"


def _print_preview(document: SpeechDocument, show_cues: bool) -> None:
    print("=== SPRECHTEXT ===")
    print(document.text)
    if not show_cues:
        return

    print("\n=== MARKDOWN-HERVORHEBUNGEN ===")
    found_cue = False
    for block_index, block in enumerate(document.blocks, start=1):
        for cue in block.emphasis_cues:
            found_cue = True
            emphasized = block.emphasized_text(cue)
            print(
                f'Block {block_index} ({block.kind}): "{emphasized}" '
                f"-> {cue.kind} [{cue.start}:{cue.end}]"
            )
    if not found_cue:
        print("Keine Markdown-Hervorhebungen gefunden.")


def _print_chunks(chunks: tuple[SpeechChunk, ...], request_overhead: int = 0) -> None:
    print(f"\n=== CHUNK-VORSCHAU ({len(chunks)} Chunks) ===")
    for chunk in chunks:
        request_count = chunk.character_count + request_overhead
        suffix = (
            f", Request mit Prefill: {request_count} Zeichen"
            if request_overhead
            else ""
        )
        print(
            f"\n--- Chunk {chunk.index}: {chunk.character_count} Zeichen{suffix} ---"
        )
        print(chunk.text)


def _print_profiles(catalog: SpeechProfileCatalog, selected_name: str | None) -> None:
    if selected_name is not None:
        profile = catalog.resolve(selected_name)
        print(f"Name: {profile.name}")
        print(f"Stimme: {profile.voice}")
        print(f"Geschwindigkeit: {profile.speed:g}")
        print(f"Anweisungen: {profile.instructions}")
        return

    entries = catalog.list_entries()
    print(f"Verfügbare Sprachprofile ({len(entries)}):")
    for entry in entries:
        profile = entry.profile
        print(
            f"- {profile.name}: Stimme={profile.voice}, "
            f"Geschwindigkeit={profile.speed:g}, Datei={entry.path}"
        )


class _CliSynthesisReporter:
    """Format progress and calculated cost without owning synthesis logic."""

    def __init__(self, config: TTSProviderConfig, *, enabled: bool) -> None:
        self._config = config
        self._enabled = enabled
        self._usage = SpeechUsageAccumulator()
        self._completed_steps = 0
        self._summary_printed = False

    def __call__(self, progress: SynthesisProgress) -> None:
        self._completed_steps += 1
        usage = progress.result.usage
        if usage is not None:
            self._usage.add(usage)
            cost = calculate_speech_cost(usage, self._config)
            usage_text = (
                f"{_format_integer(usage.input_tokens)} Input + "
                f"{_format_integer(usage.output_tokens)} Audio-Output = "
                f"{_format_integer(usage.total_tokens)} Tokens | "
                f"berechnet {_format_money(cost.total_cost)} {cost.currency}"
            )
        else:
            usage_text = "keine Usage-Daten vom Provider"
        logging.getLogger(__name__).info(
            "%s %d/%d: %d Zeichen; %s",
            progress.stage,
            progress.current,
            progress.total,
            progress.text_characters,
            usage_text,
        )
        if self._enabled:
            print(
                f"[{progress.stage} {progress.current}/{progress.total}] "
                f"{_format_integer(progress.text_characters)} Zeichen | {usage_text}"
            )

    def print_summary(self) -> None:
        if self._summary_printed or not self._enabled or self._completed_steps == 0:
            return
        self._summary_printed = True
        print("\n=== API-VERBRAUCH DIESES LAUFS ===")
        print(f"Abgeschlossene TTS-Aufrufe: {self._completed_steps}")
        if self._usage.request_count == 0:
            print("Der Provider hat keine Token-Usage zurückgegeben.")
            return
        cost = calculate_speech_cost(self._usage.usage, self._config)
        print(f"Input-Tokens: {_format_integer(self._usage.input_tokens)}")
        print(f"Audio-Output-Tokens: {_format_integer(self._usage.output_tokens)}")
        print(f"Gesamttokens: {_format_integer(self._usage.total_tokens)}")
        print(
            "Berechnete Kosten: "
            f"{_format_money(cost.input_cost)} {cost.currency} Input + "
            f"{_format_money(cost.output_cost)} {cost.currency} Audio = "
            f"{_format_money(cost.total_cost)} {cost.currency}"
        )
        print(
            "Preisstand: "
            f"{self._config.pricing_effective_date}; tatsächliche Tokens aus "
            "OpenAI speech.audio.done, Geldbetrag lokal berechnet."
        )
        print(f"Preisquelle: {self._config.pricing_source}")


def _format_integer(value: int) -> str:
    return f"{value:,}".replace(",", ".")


def _format_money(value: float) -> str:
    return f"{value:.6f}".replace(".", ",")


def _resolve_single_output_path(
    input_path: Path,
    output_path: Path | None,
    *,
    profile_name: str,
    append_profile_name: bool,
) -> Path:
    """Resolve the optional output and add a filesystem-safe profile suffix."""
    destination = output_path if output_path is not None else input_path.with_suffix(".mp3")
    if not append_profile_name:
        return destination

    safe_profile_name = re.sub(r'[^A-Za-z0-9._-]+', "-", profile_name.strip()).strip(".-")
    if not safe_profile_name:
        raise ConfigurationError(
            "Der Profilname kann nicht als Bestandteil des Ausgabedateinamens verwendet werden."
        )
    return destination.with_name(
        f"{destination.stem}_{safe_profile_name}{destination.suffix}"
    )


def _configure_logging(level: str, log_file: Path | None) -> None:
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if log_file is not None:
        try:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
        except OSError as error:
            raise ConfigurationError(
                f"Logdatei '{log_file}' konnte nicht angelegt werden: {error}"
            ) from error
    logging.basicConfig(
        level=getattr(logging, level),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=handlers,
        force=True,
    )
    for external_logger in ("openai", "httpx", "httpcore"):
        logging.getLogger(external_logger).setLevel(logging.WARNING)


def main() -> None:
    """Run the CLI without containing parser or renderer business logic."""
    argument_parser = _build_argument_parser()
    command_names = set(argument_parser._subparsers._group_actions[0].choices)
    cli_arguments = _normalize_cli_arguments(sys.argv[1:], command_names)
    arguments = argument_parser.parse_args(cli_arguments)
    reporter: _CliSynthesisReporter | None = None

    try:
        _configure_logging(arguments.log_level, arguments.log_file)
        if arguments.command == "profiles":
            _print_profiles(
                SpeechProfileCatalog(arguments.profiles_dir),
                arguments.name,
            )
            return

        if arguments.command == "merge":
            joiner_config = AudioJoinerConfig.from_file(arguments.joiner_config)
            joined_path = create_audio_joiner(joiner_config).join(
                arguments.inputs,
                arguments.output,
                overwrite=arguments.overwrite,
            )
            print(f"Audiodatei zusammengeführt: {joined_path}")
            return

        if arguments.command == "calibrate-prefill":
            provider_config = TTSProviderConfig.from_file(arguments.provider_config)
            reporter = _CliSynthesisReporter(
                provider_config,
                enabled=not arguments.no_progress,
            )
            prefill_config = PrefillConfig.from_file(arguments.prefill_config)
            profile = SpeechProfileCatalog(arguments.profiles_dir).resolve(arguments.profile)
            calibration = PrefillCalibrator(
                SpeechRenderer(profile),
                create_tts_provider(provider_config),
                prefill_config,
                profile,
                provider_config,
                progress_callback=reporter,
            ).calibrate(arguments.output, overwrite=arguments.overwrite)
            print(f"Prefill-Kalibrierung gespeichert: {arguments.output}")
            print(
                "Kalibrierungs-WAV gespeichert: "
                f"{prefill_calibration_audio_path(arguments.output)}"
            )
            print(f"Gemessene Dauer: {calibration.duration_seconds:.3f} Sekunden")
            reporter.print_summary()
            return

        parser_rules = ParserRules.from_file(arguments.parser_config)
        renderer_rules = SemanticRendererRules.from_file(arguments.renderer_config)
        markdown_parser = MarkdownParser(parser_rules)
        semantic_renderer = SemanticRenderer(renderer_rules)

        if arguments.command == "auto":
            ast_document = markdown_parser.parse(load_markdown(arguments.input))
            speech_document = semantic_renderer.render(ast_document)
            chunking_rules = ChunkingRules.from_file(arguments.chunking_config)
            arguments.command = _select_automatic_synthesis_command(
                len(speech_document.text),
                chunking_rules.max_characters,
            )
            if arguments.command == "synthesize-prefill":
                arguments.provider_config = arguments.prefill_provider_config
            print(
                f"Automatische Auswahl: {arguments.command} "
                f"({len(speech_document.text)} Zeichen, Limit "
                f"{chunking_rules.max_characters})."
            )

        if arguments.command == "preview":
            ast_document = markdown_parser.parse(load_markdown(arguments.input))
            speech_document = semantic_renderer.render(ast_document)
            _print_preview(speech_document, arguments.show_cues)
            if arguments.show_chunks:
                chunking_rules = ChunkingRules.from_file(arguments.chunking_config)
                prefill_config = (
                    PrefillConfig.from_file(arguments.prefill_config)
                    if arguments.prefill
                    else None
                )
                request_overhead = (
                    prefill_config.reserved_characters if prefill_config else 0
                )
                chunks = SemanticChunker(
                    chunking_rules,
                    reserved_characters=request_overhead,
                ).chunk(speech_document)
                _print_chunks(chunks, request_overhead)
            return

        provider_config = TTSProviderConfig.from_file(arguments.provider_config)
        reporter = _CliSynthesisReporter(
            provider_config,
            enabled=not arguments.no_progress,
        )
        profile = SpeechProfileCatalog(arguments.profiles_dir).resolve(arguments.profile)
        provider = create_tts_provider(provider_config)
        speech_renderer = SpeechRenderer(profile)
        if arguments.command == "synthesize-prefill":
            output_path = _resolve_single_output_path(
                arguments.input,
                arguments.output,
                profile_name=profile.name,
                append_profile_name=arguments.append_profile_name,
            )
            prefill_config = PrefillConfig.from_file(arguments.prefill_config)
            chunking_rules = ChunkingRules.from_file(arguments.chunking_config)
            converter = PrefillMarkdownAudioConverter(
                markdown_parser,
                semantic_renderer,
                SemanticChunker(
                    chunking_rules,
                    reserved_characters=prefill_config.reserved_characters,
                ),
                speech_renderer,
                provider,
                provider_config,
                profile,
                prefill_config,
                WavPrefillTrimmer(prefill_config),
                WavAudioJoiner(),
                create_audio_encoder(
                    AudioEncoderConfig.from_file(arguments.encoder_config)
                ),
                progress_callback=reporter,
            )
            calibrator = PrefillCalibrator(
                speech_renderer,
                provider,
                prefill_config,
                profile,
                provider_config,
                progress_callback=reporter,
            )
            result = converter.convert_with_cached_calibration(
                arguments.input,
                output_path,
                calibrator,
                arguments.calibration_cache_dir,
                refresh_calibration=arguments.refresh_calibration,
                explicit_calibration_path=arguments.calibration,
                keep_chunks=arguments.keep_chunks,
                overwrite=arguments.overwrite,
            )
            calibration_status = (
                "neu erzeugt" if result.calibration_created else "wiederverwendet"
            )
            print(
                f"Prefill-Kalibrierung {calibration_status}: "
                f"{result.calibration_path}"
            )
            print(f"Kalibrierungs-WAV: {result.calibration_audio_path}")
            print(f"Prefill-bereinigte Audiodatei erzeugt: {result.output_path}")
            if result.chunks_directory is not None:
                print(f"Chunk-Artefakte behalten: {result.chunks_directory}")
            reporter.print_summary()
            return
        if arguments.command == "synthesize":
            output_path = _resolve_single_output_path(
                arguments.input,
                arguments.output,
                profile_name=profile.name,
                append_profile_name=arguments.append_profile_name,
            )
            converter = MarkdownAudioConverter(
                markdown_parser,
                semantic_renderer,
                speech_renderer,
                provider,
                maximum_request_characters=ChunkingRules.from_file(
                    arguments.chunking_config
                ).max_characters,
                progress_callback=reporter,
            )
            output_path = converter.convert(
                arguments.input,
                output_path,
                overwrite=arguments.overwrite,
            )
            print(f"Audiodatei erzeugt: {output_path}")
            reporter.print_summary()
            return

        output_path = _resolve_single_output_path(
            arguments.input,
            arguments.output,
            profile_name=profile.name,
            append_profile_name=arguments.append_profile_name,
        )
        chunking_rules = ChunkingRules.from_file(arguments.chunking_config)
        chunk_converter = ChunkedMarkdownAudioConverter(
            markdown_parser,
            semantic_renderer,
            SemanticChunker(chunking_rules),
            speech_renderer,
            provider,
            provider_config.response_format,
            progress_callback=reporter,
        )
        result = ChunkedMarkdownMergedAudioConverter(
            chunk_converter,
            create_audio_joiner(AudioJoinerConfig.from_file(arguments.joiner_config)),
        ).convert(
            arguments.input,
            output_path,
            keep_chunks=arguments.keep_chunks,
            overwrite=arguments.overwrite,
        )
        print(f"Zusammengeführte Audiodatei erzeugt: {result.output_path}")
        if result.chunks_directory is not None:
            print(f"Chunk-Artefakte behalten: {result.chunks_directory}")
        reporter.print_summary()
    except (
        ConfigurationError,
        AudioJoinError,
        AudioOutputExistsError,
        AudioProcessingError,
        ChunkBatchConfigurationError,
        ChunkBatchGenerationError,
        ChunkOutputExistsError,
        EmptySpeechDocumentError,
        MarkdownLoadError,
        MissingApiKeyError,
        OutputFileExistsError,
        PrefillCalibrationError,
        PrefillPipelineConfigurationError,
        SpeechInputLimitError,
        TTSGenerationError,
        UnsupportedTTSProviderError,
        UnsupportedAudioJoinerError,
        UnsupportedAudioEncoderError,
        UnchunkableSpeechError,
    ) as error:
        if reporter is not None:
            reporter.print_summary()
        argument_parser.error(str(error))
