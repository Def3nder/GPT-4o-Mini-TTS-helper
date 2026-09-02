"""Application services that orchestrate independent pipeline components."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import logging
from pathlib import Path
import shutil
from tempfile import mkdtemp
from typing import Iterator

from markdown_tts.audio import (
    AudioJoiner,
    AudioEncoder,
    AudioOutputExistsError,
    WavAudioJoiner,
    WavPrefillTrimmer,
    inspect_wav,
)
from markdown_tts.chunker import SemanticChunker, SpeechChunk
from markdown_tts.config import PrefillConfig, SpeechProfile, TTSProviderConfig
from markdown_tts.loader import load_markdown
from markdown_tts.parser import MarkdownParser
from markdown_tts.prefill import (
    PrefillCalibration,
    PrefillCalibrationError,
    PrefillRequestDecorator,
    prefill_calibration_audio_path,
    prefill_calibration_cache_path,
)
from markdown_tts.semantic_renderer import SemanticRenderer, SpeechBlock, SpeechDocument
from markdown_tts.speech_renderer import SpeechRenderer
from markdown_tts.progress import SynthesisProgress, SynthesisProgressCallback
from markdown_tts.tts.base import SpeechRequest, SpeechSynthesisResult, TTSProvider


LOGGER = logging.getLogger(__name__)


class ChunkOutputExistsError(FileExistsError):
    """Raised before a chunk batch would overwrite an existing final file."""


class ChunkBatchGenerationError(RuntimeError):
    """Raised when chunk output paths cannot be prepared or published."""


class ChunkBatchConfigurationError(ValueError):
    """Raised when batch output settings cannot produce safe filenames."""


class PrefillPipelineConfigurationError(ValueError):
    """Raised before an incompatible prefill pipeline could call a provider."""


class SpeechInputLimitError(ValueError):
    """Raised before a single-request synthesis would exceed its local limit."""


@dataclass(frozen=True, slots=True)
class PrefillCalibrationResolution:
    calibration: PrefillCalibration
    path: Path
    audio_path: Path
    created: bool


@dataclass(frozen=True, slots=True)
class PrefillConversionResult:
    output_path: Path
    calibration_path: Path
    calibration_audio_path: Path
    calibration_created: bool
    chunks_directory: Path | None = None


@dataclass(frozen=True, slots=True)
class ChunkedConversionResult:
    output_path: Path
    chunks_directory: Path | None = None


class MarkdownAudioConverter:
    """Run the single-chunk Markdown-to-audio pipeline."""

    def __init__(
        self,
        parser: MarkdownParser,
        semantic_renderer: SemanticRenderer,
        speech_renderer: SpeechRenderer,
        provider: TTSProvider,
        maximum_request_characters: int | None = None,
        progress_callback: SynthesisProgressCallback | None = None,
    ) -> None:
        if maximum_request_characters is not None and maximum_request_characters <= 0:
            raise ValueError("Das Zeichenlimit für einen TTS-Request muss positiv sein.")
        self._parser = parser
        self._semantic_renderer = semantic_renderer
        self._speech_renderer = speech_renderer
        self._provider = provider
        self._maximum_request_characters = maximum_request_characters
        self._progress_callback = progress_callback

    def convert(
        self,
        input_path: str | Path,
        output_path: str | Path,
        *,
        overwrite: bool = False,
    ) -> Path:
        """Convert one short Markdown document into one audio file."""
        ast_document = self._parser.parse(load_markdown(input_path))
        speech_document = self._semantic_renderer.render(ast_document)
        request = self._speech_renderer.render(speech_document)
        if (
            self._maximum_request_characters is not None
            and len(request.text) > self._maximum_request_characters
        ):
            raise SpeechInputLimitError(
                f"Der Sprechtext enthält {len(request.text)} Zeichen und überschreitet "
                f"das konfigurierte Limit von {self._maximum_request_characters} Zeichen "
                "für einen einzelnen TTS-Request. Bitte 'synthesize-chunks' oder "
                "'synthesize-prefill' verwenden."
            )
        result = _synthesize_and_report(
            self._provider,
            request,
            output_path,
            stage="Dokument",
            current=1,
            total=1,
            progress_callback=self._progress_callback,
            overwrite=overwrite,
        )
        return result.output_path


class ChunkedMarkdownAudioConverter:
    """Generate a transactionally published set of numbered audio chunks."""

    def __init__(
        self,
        parser: MarkdownParser,
        semantic_renderer: SemanticRenderer,
        chunker: SemanticChunker,
        speech_renderer: SpeechRenderer,
        provider: TTSProvider,
        output_format: str,
        progress_callback: SynthesisProgressCallback | None = None,
    ) -> None:
        normalized_format = output_format.strip().lower().lstrip(".")
        if not normalized_format or not normalized_format.isalnum():
            raise ChunkBatchConfigurationError(
                "Das Audio-Ausgabeformat muss aus Buchstaben und Ziffern bestehen."
            )
        self._parser = parser
        self._semantic_renderer = semantic_renderer
        self._chunker = chunker
        self._speech_renderer = speech_renderer
        self._provider = provider
        self._output_format = normalized_format
        self._progress_callback = progress_callback

    def convert(
        self,
        input_path: str | Path,
        output_directory: str | Path,
        *,
        overwrite: bool = False,
    ) -> tuple[Path, ...]:
        """Generate all numbered chunk files and publish them only as a complete batch."""
        source_path = Path(input_path)
        ast_document = self._parser.parse(load_markdown(source_path))
        speech_document = self._semantic_renderer.render(ast_document)
        chunks = self._chunker.chunk(speech_document)
        if not chunks:
            self._speech_renderer.render(speech_document)

        destination_directory = Path(output_directory)
        final_paths = tuple(
            destination_directory
            / f"{source_path.stem}.part-{chunk.index:03d}.{self._output_format}"
            for chunk in chunks
        )
        self._validate_destinations(final_paths, overwrite=overwrite)

        try:
            destination_directory.mkdir(parents=True, exist_ok=True)
            with _retained_working_directory(
                prefix=f".{source_path.stem}-chunks-",
                parent=destination_directory,
                operation="Chunk-Synthese",
                keep_on_success=False,
            ) as temporary_directory:
                staging_directory = temporary_directory
                staged_paths: list[Path] = []
                for chunk, final_path in zip(chunks, final_paths, strict=True):
                    request = self._speech_renderer.render(chunk.as_document())
                    staged_path = staging_directory / final_path.name
                    _synthesize_and_report(
                        self._provider,
                        request,
                        staged_path,
                        stage="Chunk",
                        current=chunk.index,
                        total=len(chunks),
                        progress_callback=self._progress_callback,
                    )
                    staged_paths.append(staged_path)

                self._validate_destinations(final_paths, overwrite=overwrite)
                for staged_path, final_path in zip(
                    staged_paths,
                    final_paths,
                    strict=True,
                ):
                    staged_path.replace(final_path)
        except ChunkOutputExistsError:
            raise
        except OSError as error:
            raise ChunkBatchGenerationError(
                f"Chunk-Audiodateien konnten in '{destination_directory}' nicht vollständig "
                "veröffentlicht werden. Bitte Zielpfad, Schreibrechte und freien Speicher prüfen."
            ) from error

        LOGGER.info(
            "%d Audio-Chunk(s) vollständig in %s veröffentlicht.",
            len(final_paths),
            destination_directory,
        )
        return final_paths

    @staticmethod
    def _validate_destinations(
        paths: tuple[Path, ...],
        *,
        overwrite: bool,
    ) -> None:
        if overwrite:
            return
        existing = next((path for path in paths if path.exists()), None)
        if existing is not None:
            raise ChunkOutputExistsError(
                f"Chunk-Ausgabedatei '{existing}' existiert bereits. "
                "Zum Ersetzen ausdrücklich '--overwrite' verwenden."
            )


class ChunkedMarkdownMergedAudioConverter:
    """Synthesize MP3 chunks, merge them, and retain their directory on demand."""

    def __init__(
        self,
        chunk_converter: ChunkedMarkdownAudioConverter,
        audio_joiner: AudioJoiner,
    ) -> None:
        self._chunk_converter = chunk_converter
        self._audio_joiner = audio_joiner

    def convert(
        self,
        input_path: str | Path,
        output_path: str | Path,
        *,
        keep_chunks: bool = False,
        overwrite: bool = False,
    ) -> ChunkedConversionResult:
        """Publish one merged file and clean generated chunks only after success."""
        destination = Path(output_path)
        if destination.exists() and not overwrite:
            raise AudioOutputExistsError(
                f"Audio-Ausgabedatei '{destination}' existiert bereits. "
                "Zum Ersetzen ausdrücklich '--overwrite' verwenden."
            )

        chunks_directory = destination.with_suffix("")
        if chunks_directory.exists() and not chunks_directory.is_dir():
            raise ChunkBatchGenerationError(
                f"Temporärer Chunk-Pfad '{chunks_directory}' ist kein Verzeichnis."
            )

        chunk_paths = self._chunk_converter.convert(
            input_path,
            chunks_directory,
            overwrite=overwrite,
        )
        merged_path = self._audio_joiner.join(
            chunk_paths,
            destination,
            overwrite=overwrite,
        )

        retained_directory: Path | None = chunks_directory
        if not keep_chunks:
            retained_directory = self._remove_generated_chunks(
                chunk_paths,
                chunks_directory,
            )
        return ChunkedConversionResult(merged_path, retained_directory)

    @staticmethod
    def _remove_generated_chunks(
        chunk_paths: tuple[Path, ...],
        chunks_directory: Path,
    ) -> Path | None:
        try:
            for chunk_path in chunk_paths:
                chunk_path.unlink(missing_ok=True)
            chunks_directory.rmdir()
        except OSError:
            LOGGER.warning(
                "Chunk-Verzeichnis konnte nach erfolgreicher Zusammenführung nicht "
                "vollständig entfernt werden und bleibt erhalten: %s",
                chunks_directory,
            )
            return chunks_directory
        LOGGER.info("Temporäres Chunk-Verzeichnis entfernt: %s", chunks_directory)
        return None


class PrefillCalibrator:
    """Measure one fixed prefill sentence for an exact synthesis configuration."""

    def __init__(
        self,
        speech_renderer: SpeechRenderer,
        provider: TTSProvider,
        prefill_config: PrefillConfig,
        profile: SpeechProfile,
        provider_config: TTSProviderConfig,
        wav_normalizer: WavAudioJoiner | None = None,
        progress_callback: SynthesisProgressCallback | None = None,
    ) -> None:
        _require_wav_provider(provider_config)
        self._speech_renderer = speech_renderer
        self._provider = provider
        self._prefill_config = prefill_config
        self._profile = profile
        self._provider_config = provider_config
        self._wav_normalizer = wav_normalizer or WavAudioJoiner()
        self._progress_callback = progress_callback

    def calibrate(
        self,
        output_path: str | Path,
        *,
        overwrite: bool = False,
    ) -> PrefillCalibration:
        """Synthesize and persist normalized WAV plus measured JSON metadata."""
        destination = Path(output_path)
        audio_destination = prefill_calibration_audio_path(destination)
        existing = next(
            (path for path in (destination, audio_destination) if path.exists()),
            None,
        )
        if existing is not None and not overwrite:
            raise PrefillCalibrationError(
                f"Kalibrierungsdatei '{existing}' existiert bereits. "
                "Zum Ersetzen ausdrücklich '--overwrite' verwenden."
            )
        destination.parent.mkdir(parents=True, exist_ok=True)
        with _retained_working_directory(
            prefix=f".{destination.stem}-calibration-",
            parent=destination.parent,
            operation="Prefill-Kalibrierung",
            keep_on_success=False,
        ) as temporary_directory:
            raw_audio_path = temporary_directory / "raw-prefill.wav"
            normalized_audio_path = temporary_directory / "prefill.wav"
            document = SpeechDocument(
                blocks=(SpeechBlock("prefill", self._prefill_config.text),),
                block_separator="\n\n",
            )
            request = self._speech_renderer.render(document)
            _synthesize_and_report(
                self._provider,
                request,
                raw_audio_path,
                stage="Prefill-Kalibrierung",
                current=1,
                total=1,
                progress_callback=self._progress_callback,
            )
            self._wav_normalizer.join((raw_audio_path,), normalized_audio_path)
            properties = inspect_wav(normalized_audio_path)
            calibration = PrefillCalibration.create(
                self._prefill_config,
                self._profile,
                self._provider_config,
                duration_seconds=properties.duration_seconds,
                sample_rate=properties.sample_rate,
                channels=properties.channels,
                sample_width_bytes=properties.sample_width_bytes,
            )
            existing = next(
                (path for path in (destination, audio_destination) if path.exists()),
                None,
            )
            if existing is not None and not overwrite:
                raise PrefillCalibrationError(
                    f"Kalibrierungsdatei '{existing}' wurde zwischenzeitlich angelegt."
                )
            normalized_audio_path.replace(audio_destination)
            calibration.write(destination, overwrite=overwrite)

        LOGGER.info(
            "Prefill für Profil %s auf %.3f Sekunden kalibriert; WAV: %s.",
            self._profile.name,
            calibration.duration_seconds,
            audio_destination,
        )
        return calibration

    def resolve(
        self,
        cache_directory: str | Path,
        *,
        refresh: bool = False,
        explicit_path: str | Path | None = None,
    ) -> PrefillCalibrationResolution:
        """Load a matching calibration or create it automatically on cache miss."""
        destination = (
            Path(explicit_path)
            if explicit_path is not None
            else prefill_calibration_cache_path(
                cache_directory,
                self._prefill_config,
                self._profile,
                self._provider_config,
            )
        )
        audio_path = prefill_calibration_audio_path(destination)
        if destination.is_file() and audio_path.is_file() and not refresh:
            calibration = PrefillCalibration.from_file(destination)
            calibration.assert_compatible(
                self._prefill_config,
                self._profile,
                self._provider_config,
            )
            LOGGER.info("Passende Prefill-Kalibrierung aus %s geladen.", destination)
            return PrefillCalibrationResolution(
                calibration,
                destination,
                audio_path,
                False,
            )

        incomplete_cache = destination.exists() or audio_path.exists()
        if incomplete_cache and not refresh:
            LOGGER.warning(
                "Unvollständige Prefill-Kalibrierung wird neu erzeugt; vorhandene "
                "Dateien bleiben bis zur erfolgreichen Veröffentlichung erhalten: %s / %s",
                destination,
                audio_path,
            )
        calibration = self.calibrate(
            destination,
            overwrite=refresh or incomplete_cache,
        )
        return PrefillCalibrationResolution(
            calibration,
            destination,
            audio_path,
            True,
        )


class PrefillMarkdownAudioConverter:
    """Generate trimmed WAV chunks and encode one transactionally published MP3."""

    def __init__(
        self,
        parser: MarkdownParser,
        semantic_renderer: SemanticRenderer,
        chunker: SemanticChunker,
        speech_renderer: SpeechRenderer,
        provider: TTSProvider,
        provider_config: TTSProviderConfig,
        profile: SpeechProfile,
        prefill_config: PrefillConfig,
        trimmer: WavPrefillTrimmer,
        wav_joiner: WavAudioJoiner,
        encoder: AudioEncoder,
        progress_callback: SynthesisProgressCallback | None = None,
    ) -> None:
        _require_wav_provider(provider_config)
        decorator = PrefillRequestDecorator(prefill_config)
        if decorator.reserved_characters > chunker.maximum_request_characters:
            raise PrefillPipelineConfigurationError(
                "Der konfigurierte Vorspann überschreitet das gesamte Chunk-Limit."
            )
        expected_effective = (
            chunker.maximum_request_characters - decorator.reserved_characters
        )
        if chunker.effective_text_characters != expected_effective:
            raise PrefillPipelineConfigurationError(
                "Der Semantic Chunker wurde nicht mit der exakten Prefill-Zeichenreserve "
                "konfiguriert."
            )
        self._parser = parser
        self._semantic_renderer = semantic_renderer
        self._chunker = chunker
        self._speech_renderer = speech_renderer
        self._provider = provider
        self._provider_config = provider_config
        self._profile = profile
        self._prefill_config = prefill_config
        self._decorator = decorator
        self._trimmer = trimmer
        self._wav_joiner = wav_joiner
        self._encoder = encoder
        self._progress_callback = progress_callback

    def convert(
        self,
        input_path: str | Path,
        output_path: str | Path,
        calibration: PrefillCalibration,
        *,
        keep_chunks: bool = False,
        overwrite: bool = False,
    ) -> Path:
        """Run all paid calls, trims, joining, and final encoding as one transaction."""
        destination = Path(output_path)
        self._validate_output(destination, overwrite=overwrite)
        calibration.assert_compatible(
            self._prefill_config,
            self._profile,
            self._provider_config,
        )
        chunks = self._prepare_chunks(input_path)
        result, _ = self._convert_chunks(
            chunks,
            destination,
            calibration,
            keep_chunks=keep_chunks,
            overwrite=overwrite,
        )
        return result

    def _convert_chunks(
        self,
        chunks: tuple[SpeechChunk, ...],
        destination: Path,
        calibration: PrefillCalibration,
        *,
        keep_chunks: bool,
        overwrite: bool,
    ) -> tuple[Path, Path | None]:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with _retained_working_directory(
            prefix=f".{destination.stem}-prefill-",
            parent=destination.parent,
            operation="Prefill-Chunk-Verarbeitung",
            keep_on_success=keep_chunks,
        ) as temporary_directory:
            staging = temporary_directory
            trimmed_paths: list[Path] = []
            for chunk in chunks:
                request = self._decorator.decorate(
                    self._speech_renderer.render(chunk.as_document())
                )
                if len(request.text) > self._chunker.maximum_request_characters:
                    raise PrefillPipelineConfigurationError(
                        f"Prefill-Request {chunk.index} überschreitet das Limit von "
                        f"{self._chunker.maximum_request_characters} Zeichen."
                    )
                raw_path = staging / f"raw-{chunk.index:03d}.wav"
                trimmed_path = staging / f"trimmed-{chunk.index:03d}.wav"
                _synthesize_and_report(
                    self._provider,
                    request,
                    raw_path,
                    stage="Prefill-Chunk",
                    current=chunk.index,
                    total=len(chunks),
                    progress_callback=self._progress_callback,
                )
                raw_properties = inspect_wav(raw_path)
                if (
                    raw_properties.sample_rate != calibration.sample_rate
                    or raw_properties.channels != calibration.channels
                    or raw_properties.sample_width_bytes != calibration.sample_width_bytes
                ):
                    raise PrefillCalibrationError(
                        f"WAV-Parameter von Chunk {chunk.index} weichen von der Kalibrierung "
                        "ab. Bitte neu kalibrieren."
                    )
                self._trimmer.trim(
                    raw_path,
                    trimmed_path,
                    expected_boundary_seconds=calibration.duration_seconds,
                )
                trimmed_paths.append(trimmed_path)

            combined_path = staging / "combined.wav"
            self._wav_joiner.join(trimmed_paths, combined_path)
            staged_output = staging / destination.name
            self._encoder.encode(combined_path, staged_output)
            self._validate_destination(destination, overwrite=overwrite)
            staged_output.replace(destination)

        LOGGER.info(
            "%d Prefill-Chunk(s) zu %s verarbeitet.",
            len(chunks),
            destination,
        )
        return destination, staging if keep_chunks else None

    def convert_with_cached_calibration(
        self,
        input_path: str | Path,
        output_path: str | Path,
        calibrator: PrefillCalibrator,
        calibration_cache_directory: str | Path,
        *,
        refresh_calibration: bool = False,
        explicit_calibration_path: str | Path | None = None,
        keep_chunks: bool = False,
        overwrite: bool = False,
    ) -> PrefillConversionResult:
        """Resolve calibration automatically, then run the transactional conversion."""
        destination = Path(output_path)
        self._validate_output(destination, overwrite=overwrite)
        chunks = self._prepare_chunks(input_path)
        resolution = calibrator.resolve(
            calibration_cache_directory,
            refresh=refresh_calibration,
            explicit_path=explicit_calibration_path,
        )
        resolution.calibration.assert_compatible(
            self._prefill_config,
            self._profile,
            self._provider_config,
        )
        result, chunks_directory = self._convert_chunks(
            chunks,
            destination,
            resolution.calibration,
            keep_chunks=keep_chunks,
            overwrite=overwrite,
        )
        return PrefillConversionResult(
            output_path=result,
            calibration_path=resolution.path,
            calibration_audio_path=resolution.audio_path,
            calibration_created=resolution.created,
            chunks_directory=chunks_directory,
        )

    def _prepare_chunks(self, input_path: str | Path) -> tuple[SpeechChunk, ...]:
        source_path = Path(input_path)
        ast_document = self._parser.parse(load_markdown(source_path))
        speech_document = self._semantic_renderer.render(ast_document)
        chunks = self._chunker.chunk(speech_document)
        if not chunks:
            self._speech_renderer.render(speech_document)
        return chunks

    @staticmethod
    def _validate_output(destination: Path, *, overwrite: bool) -> None:
        if destination.suffix.casefold() != ".mp3":
            raise PrefillPipelineConfigurationError(
                "Die finale Prefill-Ausgabedatei muss auf '.mp3' enden."
            )
        PrefillMarkdownAudioConverter._validate_destination(
            destination,
            overwrite=overwrite,
        )

    @staticmethod
    def _validate_destination(destination: Path, *, overwrite: bool) -> None:
        if destination.exists() and not overwrite:
            raise AudioOutputExistsError(
                f"Audio-Ausgabedatei '{destination}' existiert bereits. "
                "Zum Ersetzen ausdrücklich '--overwrite' verwenden."
            )


def _require_wav_provider(config: TTSProviderConfig) -> None:
    if config.response_format.casefold() != "wav":
        raise PrefillPipelineConfigurationError(
            "Der Prefill-Modus benötigt eine TTS-Provider-Konfiguration mit "
            "'response_format: wav'."
        )


def _synthesize_and_report(
    provider: TTSProvider,
    request: SpeechRequest,
    output_path: str | Path,
    *,
    stage: str,
    current: int,
    total: int,
    progress_callback: SynthesisProgressCallback | None,
    overwrite: bool = False,
) -> SpeechSynthesisResult:
    result = provider.synthesize(request, output_path, overwrite=overwrite)
    progress = SynthesisProgress(
        stage=stage,
        current=current,
        total=total,
        text_characters=len(request.text),
        result=result,
    )
    LOGGER.info(
        "%s %d/%d synthetisiert: %d Zeichen -> %s",
        stage,
        current,
        total,
        len(request.text),
        result.output_path,
    )
    if progress_callback is not None:
        progress_callback(progress)
    return result


@contextmanager
def _retained_working_directory(
    *,
    prefix: str,
    parent: Path,
    operation: str,
    keep_on_success: bool,
) -> Iterator[Path]:
    """Retain failures and optionally successful diagnostic artifacts."""
    directory = Path(mkdtemp(prefix=prefix, dir=parent))
    try:
        yield directory
    except BaseException:
        LOGGER.error(
            "%s fehlgeschlagen. Diagnoseartefakte bleiben erhalten: %s",
            operation,
            directory,
        )
        raise
    else:
        if keep_on_success:
            LOGGER.info(
                "%s erfolgreich. Chunk-Artefakte bleiben erhalten: %s",
                operation,
                directory,
            )
            return
        try:
            shutil.rmtree(directory)
        except OSError:
            LOGGER.warning(
                "Arbeitsverzeichnis konnte nach erfolgreicher Verarbeitung nicht "
                "entfernt werden: %s",
                directory,
            )
