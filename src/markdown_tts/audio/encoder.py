"""Provider-independent final audio encoding and FFmpeg implementation."""

from __future__ import annotations

from collections.abc import Callable
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Any, Protocol

from markdown_tts.audio.base import (
    AudioDependencyError,
    AudioOutputExistsError,
    AudioProcessingError,
)
from markdown_tts.audio.wav_support import inspect_wav
from markdown_tts.config import AudioEncoderConfig


class AudioEncodingError(AudioProcessingError):
    """Raised when final audio encoding fails validation."""


class UnsupportedAudioEncoderError(ValueError):
    """Raised when configuration requests an unavailable encoder backend."""


class AudioEncoder(Protocol):
    def encode(
        self,
        input_path: str | Path,
        output_path: str | Path,
        *,
        overwrite: bool = False,
    ) -> Path:
        """Encode one source file and publish the validated result atomically."""
        ...


CommandRunner = Callable[..., subprocess.CompletedProcess[str]]
ExecutableResolver = Callable[[str], str | None]


class FFmpegAudioEncoder:
    """Encode one PCM WAV source to the configured final format exactly once."""

    def __init__(
        self,
        config: AudioEncoderConfig,
        *,
        runner: CommandRunner = subprocess.run,
        executable_resolver: ExecutableResolver = shutil.which,
    ) -> None:
        self._config = config
        self._runner = runner
        self._ffmpeg = self._resolve(config.executable, executable_resolver)
        self._ffprobe = self._resolve(config.probe_executable, executable_resolver)

    def encode(
        self,
        input_path: str | Path,
        output_path: str | Path,
        *,
        overwrite: bool = False,
    ) -> Path:
        source = Path(input_path)
        destination = Path(output_path)
        if not source.is_file() or source.suffix.casefold() != ".wav":
            raise AudioEncodingError(
                f"Encoder-Eingabe '{source}' muss eine vorhandene WAV-Datei sein."
            )
        if source.resolve() == destination.resolve():
            raise AudioEncodingError("Encoder-Eingabe und -Ausgabe müssen verschieden sein.")
        self._validate_destination(destination, overwrite=overwrite)
        source_properties = inspect_wav(source)

        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=f".{destination.stem}-",
                suffix=destination.suffix,
                dir=destination.parent,
            )
            os.close(descriptor)
        except OSError as error:
            raise AudioEncodingError(
                f"Temporäre Encoder-Ausgabe für '{destination}' konnte nicht angelegt werden."
            ) from error
        temporary_path = Path(temporary_name)
        temporary_path.unlink(missing_ok=True)
        command = [
            self._ffmpeg,
            "-hide_banner",
            "-loglevel",
            self._config.log_level,
            "-i",
            str(source),
            "-map",
            "0:a:0",
            "-c:a",
            self._config.codec,
            "-b:a",
            self._config.bitrate,
            "-map_metadata",
            "-1",
            str(temporary_path),
        ]
        try:
            completed = self._run(command, "FFmpeg")
            if (
                completed.returncode != 0
                or not temporary_path.is_file()
                or temporary_path.stat().st_size == 0
            ):
                raise AudioEncodingError(
                    "FFmpeg konnte die finale Audiodatei nicht kodieren: "
                    f"{completed.stderr.strip() or 'keine Ausgabedatei erzeugt'}"
                )
            codec_name, duration_seconds = self._probe(temporary_path)
            if codec_name.casefold() != self._config.expected_codec_name.casefold():
                raise AudioEncodingError(
                    f"Kodierte Datei besitzt Codec '{codec_name}' statt "
                    f"'{self._config.expected_codec_name}'."
                )
            difference = abs(duration_seconds - source_properties.duration_seconds)
            if difference > self._config.duration_tolerance_seconds:
                raise AudioEncodingError(
                    "Die Dauer der kodierten Datei weicht zu stark von der WAV-Quelle ab "
                    f"({difference:.3f} Sekunden)."
                )
            self._validate_destination(destination, overwrite=overwrite)
            temporary_path.replace(destination)
        except AudioOutputExistsError:
            raise
        except OSError as error:
            raise AudioEncodingError(
                f"Kodierte Audiodatei '{destination}' konnte nicht gespeichert werden."
            ) from error
        finally:
            temporary_path.unlink(missing_ok=True)
        return destination

    def _probe(self, path: Path) -> tuple[str, float]:
        command = [
            self._ffprobe,
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            "stream=codec_name:format=duration",
            "-of",
            "json",
            str(path),
        ]
        completed = self._run(command, "FFprobe")
        if completed.returncode != 0:
            raise AudioEncodingError(
                f"Kodierte Datei konnte nicht geprüft werden: {completed.stderr.strip()}"
            )
        try:
            payload: Any = json.loads(completed.stdout)
            return str(payload["streams"][0]["codec_name"]), float(
                payload["format"]["duration"]
            )
        except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise AudioEncodingError("FFprobe lieferte keine verwertbaren Audiodaten.") from error

    def _run(
        self,
        command: list[str],
        tool_name: str,
    ) -> subprocess.CompletedProcess[str]:
        try:
            return self._runner(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self._config.timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            raise AudioEncodingError(
                f"{tool_name} wurde nach {self._config.timeout_seconds:g} Sekunden abgebrochen."
            ) from error
        except OSError as error:
            raise AudioDependencyError(
                f"{tool_name} konnte nicht gestartet werden. Bitte Installation und Pfad prüfen."
            ) from error

    @staticmethod
    def _resolve(name: str, resolver: ExecutableResolver) -> str:
        resolved = resolver(name)
        if resolved is None:
            raise AudioDependencyError(
                f"Audio-Werkzeug '{name}' wurde nicht gefunden. Bitte FFmpeg installieren "
                "oder den Pfad in config/audio_encoder.json konfigurieren."
            )
        return resolved

    @staticmethod
    def _validate_destination(destination: Path, *, overwrite: bool) -> None:
        if destination.exists() and not overwrite:
            raise AudioOutputExistsError(
                f"Audio-Ausgabedatei '{destination}' existiert bereits. "
                "Zum Ersetzen ausdrücklich '--overwrite' verwenden."
            )


def create_audio_encoder(config: AudioEncoderConfig) -> AudioEncoder:
    """Create the configured final audio encoder behind a shared protocol."""
    if config.backend.casefold() == "ffmpeg":
        return FFmpegAudioEncoder(config)
    raise UnsupportedAudioEncoderError(
        f"Audio-Encoder '{config.backend}' wird nicht unterstützt. Verfügbar: ffmpeg."
    )
