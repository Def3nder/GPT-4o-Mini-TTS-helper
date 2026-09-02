"""Loading and validation for external project configuration."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any, Pattern


class ConfigurationError(ValueError):
    """Base error for invalid project configuration."""


class ParserConfigurationError(ConfigurationError):
    """Raised when parser rules are missing or invalid."""


class SemanticRendererConfigurationError(ConfigurationError):
    """Raised when semantic renderer rules are missing or invalid."""


class ChunkingConfigurationError(ConfigurationError):
    """Raised when semantic chunking rules are missing or invalid."""


class TTSProviderConfigurationError(ConfigurationError):
    """Raised when TTS provider settings are missing or invalid."""


class AudioJoinerConfigurationError(ConfigurationError):
    """Raised when audio-joiner settings are missing or invalid."""


class AudioEncoderConfigurationError(ConfigurationError):
    """Raised when final audio-encoding settings are missing or invalid."""


class PrefillConfigurationError(ConfigurationError):
    """Raised when prefill and silence-detection settings are invalid."""


class SpeechProfileConfigurationError(ConfigurationError):
    """Raised when a speech profile is missing or invalid."""


def _load_json_object(
    path: str | Path,
    description: str,
    error_type: type[ConfigurationError],
) -> dict[str, Any]:
    config_path = Path(path)
    try:
        raw: Any = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise error_type(
            f"{description} '{config_path}' konnte nicht gelesen werden: {error}"
        ) from error
    if not isinstance(raw, dict):
        raise error_type(f"{description} muss ein JSON-Objekt sein.")
    return raw


@dataclass(frozen=True, slots=True)
class ParserRules:
    front_matter_delimiter: str
    remove_html_comments: bool
    remove_urls: bool
    url_pattern: Pattern[str]
    source_prefixes: tuple[str, ...]
    date_line_pattern: Pattern[str]

    @classmethod
    def from_file(cls, path: str | Path) -> ParserRules:
        """Load parser rules from a UTF-8 encoded JSON file."""
        raw = _load_json_object(path, "Parser-Konfiguration", ParserConfigurationError)

        required = {
            "front_matter_delimiter": str,
            "remove_html_comments": bool,
            "remove_urls": bool,
            "url_pattern": str,
            "source_prefixes": list,
            "date_line_pattern": str,
        }
        for key, expected_type in required.items():
            if key not in raw or not isinstance(raw[key], expected_type):
                raise ParserConfigurationError(
                    f"Konfigurationswert '{key}' fehlt oder besitzt den falschen Typ."
                )

        prefixes = raw["source_prefixes"]
        if not all(isinstance(prefix, str) and prefix for prefix in prefixes):
            raise ParserConfigurationError("'source_prefixes' darf nur nichtleere Texte enthalten.")

        try:
            url_pattern = re.compile(raw["url_pattern"])
            date_line_pattern = re.compile(raw["date_line_pattern"])
        except re.error as error:
            raise ParserConfigurationError(f"Ungültiger regulärer Ausdruck: {error}") from error

        delimiter = raw["front_matter_delimiter"]
        if not delimiter:
            raise ParserConfigurationError("'front_matter_delimiter' darf nicht leer sein.")

        return cls(
            front_matter_delimiter=delimiter,
            remove_html_comments=raw["remove_html_comments"],
            remove_urls=raw["remove_urls"],
            url_pattern=url_pattern,
            source_prefixes=tuple(prefixes),
            date_line_pattern=date_line_pattern,
        )


@dataclass(frozen=True, slots=True)
class SemanticRendererRules:
    ordered_list_markers: tuple[str, ...]
    ordered_list_fallback: str
    unordered_list_marker: str
    list_marker_suffix: str
    heading_suffix: str
    block_separator: str
    list_item_separator: str
    quote_prefix: str
    table_cell_separator: str
    table_row_separator: str
    footnote_prefix: str
    speak_tables: bool
    speak_code_blocks: bool
    speak_footnotes: bool
    speak_image_alt_text: bool
    speak_inline_code: bool
    remove_punctuation_only_blocks: bool

    @classmethod
    def from_file(cls, path: str | Path) -> SemanticRendererRules:
        """Load semantic speech-rendering rules from a UTF-8 JSON file."""
        raw = _load_json_object(
            path,
            "Semantic-Renderer-Konfiguration",
            SemanticRendererConfigurationError,
        )
        required = {
            "ordered_list_markers": list,
            "ordered_list_fallback": str,
            "unordered_list_marker": str,
            "list_marker_suffix": str,
            "heading_suffix": str,
            "block_separator": str,
            "list_item_separator": str,
            "quote_prefix": str,
            "table_cell_separator": str,
            "table_row_separator": str,
            "footnote_prefix": str,
            "speak_tables": bool,
            "speak_code_blocks": bool,
            "speak_footnotes": bool,
            "speak_image_alt_text": bool,
            "speak_inline_code": bool,
            "remove_punctuation_only_blocks": bool,
        }
        for key, expected_type in required.items():
            if key not in raw or not isinstance(raw[key], expected_type):
                raise SemanticRendererConfigurationError(
                    f"Konfigurationswert '{key}' fehlt oder besitzt den falschen Typ."
                )

        markers = raw["ordered_list_markers"]
        if not markers or not all(isinstance(marker, str) and marker for marker in markers):
            raise SemanticRendererConfigurationError(
                "'ordered_list_markers' muss nichtleere Texte enthalten."
            )
        try:
            raw["ordered_list_fallback"].format(number=1)
            raw["footnote_prefix"].format(label="1")
        except (KeyError, ValueError) as error:
            raise SemanticRendererConfigurationError(
                "'ordered_list_fallback' muss den Platzhalter '{number}' unterstützen."
            ) from error

        return cls(
            ordered_list_markers=tuple(markers),
            ordered_list_fallback=raw["ordered_list_fallback"],
            unordered_list_marker=raw["unordered_list_marker"],
            list_marker_suffix=raw["list_marker_suffix"],
            heading_suffix=raw["heading_suffix"],
            block_separator=raw["block_separator"],
            list_item_separator=raw["list_item_separator"],
            quote_prefix=raw["quote_prefix"],
            table_cell_separator=raw["table_cell_separator"],
            table_row_separator=raw["table_row_separator"],
            footnote_prefix=raw["footnote_prefix"],
            speak_tables=raw["speak_tables"],
            speak_code_blocks=raw["speak_code_blocks"],
            speak_footnotes=raw["speak_footnotes"],
            speak_image_alt_text=raw["speak_image_alt_text"],
            speak_inline_code=raw["speak_inline_code"],
            remove_punctuation_only_blocks=raw["remove_punctuation_only_blocks"],
        )


@dataclass(frozen=True, slots=True)
class ChunkingRules:
    max_characters: int
    preferred_minimum_characters: int
    minimum_split_ratio: float
    start_new_chunk_at_headings: bool
    structural_break_characters: str
    sentence_end_characters: str
    clause_end_characters: str
    comma_characters: str
    allow_whitespace_fallback: bool

    @classmethod
    def from_file(cls, path: str | Path) -> ChunkingRules:
        """Load provider-independent semantic chunking rules from JSON."""
        raw = _load_json_object(
            path,
            "Chunking-Konfiguration",
            ChunkingConfigurationError,
        )
        required = {
            "max_characters": int,
            "preferred_minimum_characters": int,
            "minimum_split_ratio": (int, float),
            "start_new_chunk_at_headings": bool,
            "structural_break_characters": str,
            "sentence_end_characters": str,
            "clause_end_characters": str,
            "comma_characters": str,
            "allow_whitespace_fallback": bool,
        }
        for key, expected_type in required.items():
            value = raw.get(key)
            if isinstance(value, bool) and expected_type is not bool:
                valid = False
            else:
                valid = isinstance(value, expected_type)
            if not valid:
                raise ChunkingConfigurationError(
                    f"Konfigurationswert '{key}' fehlt oder besitzt den falschen Typ."
                )

        max_characters = raw["max_characters"]
        preferred_minimum = raw["preferred_minimum_characters"]
        minimum_split_ratio = float(raw["minimum_split_ratio"])
        if max_characters <= 0:
            raise ChunkingConfigurationError("'max_characters' muss positiv sein.")
        if preferred_minimum <= 0 or preferred_minimum > max_characters:
            raise ChunkingConfigurationError(
                "'preferred_minimum_characters' muss positiv und höchstens so groß wie "
                "'max_characters' sein."
            )
        if not 0 < minimum_split_ratio <= 1:
            raise ChunkingConfigurationError(
                "'minimum_split_ratio' muss größer als 0 und höchstens 1 sein."
            )

        boundary_keys = (
            "structural_break_characters",
            "sentence_end_characters",
            "clause_end_characters",
            "comma_characters",
        )
        if not all(raw[key] for key in boundary_keys):
            raise ChunkingConfigurationError(
                "Die konfigurierten Trennzeichen-Gruppen dürfen nicht leer sein."
            )

        return cls(
            max_characters=max_characters,
            preferred_minimum_characters=preferred_minimum,
            minimum_split_ratio=minimum_split_ratio,
            start_new_chunk_at_headings=raw["start_new_chunk_at_headings"],
            structural_break_characters=raw["structural_break_characters"],
            sentence_end_characters=raw["sentence_end_characters"],
            clause_end_characters=raw["clause_end_characters"],
            comma_characters=raw["comma_characters"],
            allow_whitespace_fallback=raw["allow_whitespace_fallback"],
        )


@dataclass(frozen=True, slots=True)
class TTSProviderConfig:
    provider: str
    api_key_environment_variable: str
    model: str
    response_format: str
    stream_format: str
    timeout_seconds: float
    max_retries: int
    pricing_currency: str
    input_token_price_per_million: float
    output_token_price_per_million: float
    pricing_effective_date: str
    pricing_source: str

    @classmethod
    def from_file(cls, path: str | Path) -> TTSProviderConfig:
        """Load provider settings without ever loading or storing the API key itself."""
        raw = _load_json_object(path, "TTS-Provider-Konfiguration", TTSProviderConfigurationError)
        string_fields = (
            "provider",
            "api_key_environment_variable",
            "model",
            "response_format",
            "stream_format",
        )
        for key in string_fields:
            if not isinstance(raw.get(key), str) or not raw[key].strip():
                raise TTSProviderConfigurationError(
                    f"Konfigurationswert '{key}' muss ein nichtleerer Text sein."
                )

        timeout = raw.get("timeout_seconds")
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout <= 0:
            raise TTSProviderConfigurationError(
                "'timeout_seconds' muss eine positive Zahl sein."
            )
        retries = raw.get("max_retries")
        if isinstance(retries, bool) or not isinstance(retries, int) or retries < 0:
            raise TTSProviderConfigurationError(
                "'max_retries' muss eine nichtnegative Ganzzahl sein."
            )
        stream_format = raw["stream_format"].casefold()
        if stream_format not in {"audio", "sse"}:
            raise TTSProviderConfigurationError(
                "'stream_format' muss 'audio' oder 'sse' sein."
            )
        pricing = raw.get("pricing")
        if not isinstance(pricing, dict):
            raise TTSProviderConfigurationError(
                "'pricing' muss ein Objekt mit den dokumentierten Tokenpreisen sein."
            )
        for key in ("currency", "effective_date", "source"):
            if not isinstance(pricing.get(key), str) or not pricing[key].strip():
                raise TTSProviderConfigurationError(
                    f"Pricing-Wert '{key}' muss ein nichtleerer Text sein."
                )
        price_values: dict[str, float] = {}
        for key in (
            "input_text_tokens_per_million",
            "output_audio_tokens_per_million",
        ):
            value = pricing.get(key)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
                raise TTSProviderConfigurationError(
                    f"Pricing-Wert '{key}' muss eine nichtnegative Zahl sein."
                )
            price_values[key] = float(value)

        return cls(
            provider=raw["provider"],
            api_key_environment_variable=raw["api_key_environment_variable"],
            model=raw["model"],
            response_format=raw["response_format"],
            stream_format=stream_format,
            timeout_seconds=float(timeout),
            max_retries=retries,
            pricing_currency=pricing["currency"].strip().upper(),
            input_token_price_per_million=price_values[
                "input_text_tokens_per_million"
            ],
            output_token_price_per_million=price_values[
                "output_audio_tokens_per_million"
            ],
            pricing_effective_date=pricing["effective_date"].strip(),
            pricing_source=pricing["source"].strip(),
        )


@dataclass(frozen=True, slots=True)
class AudioJoinerConfig:
    backend: str
    executable: str
    probe_executable: str
    codec_mode: str
    log_level: str
    timeout_seconds: float
    duration_tolerance_seconds: float

    @classmethod
    def from_file(cls, path: str | Path) -> AudioJoinerConfig:
        """Load audio-joining settings from a UTF-8 JSON file."""
        raw = _load_json_object(
            path,
            "Audio-Joiner-Konfiguration",
            AudioJoinerConfigurationError,
        )
        string_fields = (
            "backend",
            "executable",
            "probe_executable",
            "codec_mode",
            "log_level",
        )
        for key in string_fields:
            if not isinstance(raw.get(key), str) or not raw[key].strip():
                raise AudioJoinerConfigurationError(
                    f"Konfigurationswert '{key}' muss ein nichtleerer Text sein."
                )

        timeout = raw.get("timeout_seconds")
        tolerance = raw.get("duration_tolerance_seconds")
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout <= 0:
            raise AudioJoinerConfigurationError(
                "'timeout_seconds' muss eine positive Zahl sein."
            )
        if (
            isinstance(tolerance, bool)
            or not isinstance(tolerance, (int, float))
            or tolerance < 0
        ):
            raise AudioJoinerConfigurationError(
                "'duration_tolerance_seconds' muss eine nichtnegative Zahl sein."
            )

        return cls(
            backend=raw["backend"],
            executable=raw["executable"],
            probe_executable=raw["probe_executable"],
            codec_mode=raw["codec_mode"],
            log_level=raw["log_level"],
            timeout_seconds=float(timeout),
            duration_tolerance_seconds=float(tolerance),
        )


@dataclass(frozen=True, slots=True)
class AudioEncoderConfig:
    backend: str
    executable: str
    probe_executable: str
    codec: str
    expected_codec_name: str
    bitrate: str
    log_level: str
    timeout_seconds: float
    duration_tolerance_seconds: float

    @classmethod
    def from_file(cls, path: str | Path) -> AudioEncoderConfig:
        """Load final audio-encoding settings from a UTF-8 JSON file."""
        raw = _load_json_object(
            path,
            "Audio-Encoder-Konfiguration",
            AudioEncoderConfigurationError,
        )
        string_fields = (
            "backend",
            "executable",
            "probe_executable",
            "codec",
            "expected_codec_name",
            "bitrate",
            "log_level",
        )
        for key in string_fields:
            if not isinstance(raw.get(key), str) or not raw[key].strip():
                raise AudioEncoderConfigurationError(
                    f"Konfigurationswert '{key}' muss ein nichtleerer Text sein."
                )

        timeout = raw.get("timeout_seconds")
        tolerance = raw.get("duration_tolerance_seconds")
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout <= 0:
            raise AudioEncoderConfigurationError(
                "'timeout_seconds' muss eine positive Zahl sein."
            )
        if (
            isinstance(tolerance, bool)
            or not isinstance(tolerance, (int, float))
            or tolerance < 0
        ):
            raise AudioEncoderConfigurationError(
                "'duration_tolerance_seconds' muss eine nichtnegative Zahl sein."
            )

        return cls(
            backend=raw["backend"],
            executable=raw["executable"],
            probe_executable=raw["probe_executable"],
            codec=raw["codec"],
            expected_codec_name=raw["expected_codec_name"],
            bitrate=raw["bitrate"],
            log_level=raw["log_level"],
            timeout_seconds=float(timeout),
            duration_tolerance_seconds=float(tolerance),
        )


@dataclass(frozen=True, slots=True)
class PrefillConfig:
    text: str
    separator: str
    analysis_window_milliseconds: float
    minimum_quiet_milliseconds: float
    quiet_threshold_dbfs: float
    search_before_seconds: float
    search_after_seconds: float
    cut_safety_seconds: float
    minimum_remaining_seconds: float

    @property
    def request_prefix(self) -> str:
        """Return the exact text prepended to every provider request."""
        return f"{self.text}{self.separator}"

    @property
    def reserved_characters(self) -> int:
        """Return input characters unavailable to the actual chunk body."""
        return len(self.request_prefix)

    @classmethod
    def from_file(cls, path: str | Path) -> PrefillConfig:
        """Load prefill and WAV-boundary detection settings from JSON."""
        raw = _load_json_object(
            path,
            "Prefill-Konfiguration",
            PrefillConfigurationError,
        )
        for key in ("text", "separator"):
            if not isinstance(raw.get(key), str) or not raw[key]:
                raise PrefillConfigurationError(
                    f"Konfigurationswert '{key}' muss ein nichtleerer Text sein."
                )

        numeric_fields = (
            "analysis_window_milliseconds",
            "minimum_quiet_milliseconds",
            "quiet_threshold_dbfs",
            "search_before_seconds",
            "search_after_seconds",
            "cut_safety_seconds",
            "minimum_remaining_seconds",
        )
        values: dict[str, float] = {}
        for key in numeric_fields:
            value = raw.get(key)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise PrefillConfigurationError(
                    f"Konfigurationswert '{key}' muss eine Zahl sein."
                )
            values[key] = float(value)

        if values["analysis_window_milliseconds"] <= 0:
            raise PrefillConfigurationError(
                "'analysis_window_milliseconds' muss positiv sein."
            )
        if values["minimum_quiet_milliseconds"] <= 0:
            raise PrefillConfigurationError(
                "'minimum_quiet_milliseconds' muss positiv sein."
            )
        if not -100 <= values["quiet_threshold_dbfs"] < 0:
            raise PrefillConfigurationError(
                "'quiet_threshold_dbfs' muss mindestens -100 und kleiner als 0 sein."
            )
        if values["search_before_seconds"] < 0 or values["search_after_seconds"] < 0:
            raise PrefillConfigurationError(
                "Die Prefill-Suchbereiche dürfen nicht negativ sein."
            )
        if values["cut_safety_seconds"] < 0:
            raise PrefillConfigurationError(
                "'cut_safety_seconds' darf nicht negativ sein."
            )
        if values["minimum_remaining_seconds"] <= 0:
            raise PrefillConfigurationError(
                "'minimum_remaining_seconds' muss positiv sein."
            )

        return cls(
            text=raw["text"],
            separator=raw["separator"],
            **values,
        )


@dataclass(frozen=True, slots=True)
class SpeechProfile:
    name: str
    voice: str
    instructions: str
    speed: float = 1.0

    @classmethod
    def from_file(cls, path: str | Path) -> SpeechProfile:
        """Load a provider-independent speech profile from JSON."""
        raw = _load_json_object(path, "Sprachprofil", SpeechProfileConfigurationError)
        required = (
            "name",
            "voice",
            "instructions",
        )
        for key in required:
            if not isinstance(raw.get(key), str):
                raise SpeechProfileConfigurationError(
                    f"Konfigurationswert '{key}' fehlt oder ist kein Text."
                )
        if not raw["name"].strip() or not raw["voice"].strip():
            raise SpeechProfileConfigurationError("Profilname und Stimme dürfen nicht leer sein.")

        speed = raw.get("speed", 1.0)
        if isinstance(speed, bool) or not isinstance(speed, (int, float)):
            raise SpeechProfileConfigurationError(
                "Konfigurationswert 'speed' muss eine Zahl sein."
            )
        if not 0.25 <= float(speed) <= 4.0:
            raise SpeechProfileConfigurationError(
                "Konfigurationswert 'speed' muss zwischen 0.25 und 4.0 liegen."
            )

        return cls(
            name=raw["name"],
            voice=raw["voice"],
            instructions=raw["instructions"],
            speed=float(speed),
        )
