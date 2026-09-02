"""Lossless stream-copy audio joining through FFmpeg."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
import json
import logging
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
from typing import Any

from markdown_tts.audio.base import (
    AudioCompatibilityError,
    AudioDependencyError,
    AudioJoinError,
    AudioOutputExistsError,
)
from markdown_tts.config import AudioJoinerConfig


LOGGER = logging.getLogger(__name__)

CommandRunner = Callable[..., subprocess.CompletedProcess[str]]
ExecutableResolver = Callable[[str], str | None]


@dataclass(frozen=True, slots=True)
class AudioProperties:
    codec_name: str
    sample_rate: int
    channels: int
    duration_seconds: float

    @property
    def stream_signature(self) -> tuple[str, int, int]:
        """Return parameters that must match for stream-copy concatenation."""
        return self.codec_name, self.sample_rate, self.channels


class FFmpegAudioJoiner:
    """Join compatible audio streams without decoding or re-encoding them."""

    def __init__(
        self,
        config: AudioJoinerConfig,
        *,
        runner: CommandRunner = subprocess.run,
        executable_resolver: ExecutableResolver = shutil.which,
    ) -> None:
        if config.codec_mode.casefold() != "copy":
            raise AudioCompatibilityError(
                "Der FFmpeg-Audio-Joiner unterstützt derzeit nur 'codec_mode: copy'."
            )
        self._config = config
        self._runner = runner
        self._ffmpeg = self._resolve_executable(config.executable, executable_resolver)
        self._ffprobe = self._resolve_executable(
            config.probe_executable,
            executable_resolver,
        )

    def join(
        self,
        input_paths: Sequence[str | Path],
        output_path: str | Path,
        *,
        overwrite: bool = False,
    ) -> Path:
        """Validate and concatenate compatible audio streams atomically."""
        inputs = tuple(Path(path) for path in input_paths)
        if len(inputs) < 2:
            raise AudioJoinError(
                "Zum Zusammenfügen werden mindestens zwei Audiodateien benötigt."
            )
        for input_path in inputs:
            if not input_path.is_file():
                raise AudioJoinError(
                    f"Audio-Eingabedatei '{input_path}' wurde nicht gefunden."
                )

        destination = Path(output_path)
        resolved_destination = destination.resolve()
        if any(path.resolve() == resolved_destination for path in inputs):
            raise AudioJoinError(
                "Die Zieldatei darf nicht zugleich eine der Eingabedateien sein."
            )
        self._validate_destination(destination, overwrite=overwrite)

        suffixes = {path.suffix.casefold() for path in inputs}
        if len(suffixes) != 1 or destination.suffix.casefold() not in suffixes:
            raise AudioCompatibilityError(
                "Für verlustfreies Stream-Copy müssen alle Ein- und Ausgabedateien "
                "dieselbe Dateiendung besitzen."
            )

        properties = tuple(self._probe(path) for path in inputs)
        reference_signature = properties[0].stream_signature
        incompatible = next(
            (
                (path, item)
                for path, item in zip(inputs, properties, strict=True)
                if item.stream_signature != reference_signature
            ),
            None,
        )
        if incompatible is not None:
            path, item = incompatible
            raise AudioCompatibilityError(
                f"Audio-Eingabedatei '{path}' besitzt inkompatible Streamparameter: "
                f"{item.stream_signature}; erwartet: {reference_signature}."
            )

        expected_duration = sum(item.duration_seconds for item in properties)
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            with TemporaryDirectory(
                prefix=f".{destination.stem}-join-",
                dir=destination.parent,
            ) as temporary_directory:
                temporary_root = Path(temporary_directory)
                concat_file = temporary_root / "inputs.ffconcat"
                concat_file.write_text(
                    self._build_concat_manifest(inputs),
                    encoding="utf-8",
                )
                temporary_output = temporary_root / f"joined{destination.suffix}"
                self._concatenate(concat_file, temporary_output)
                output_properties = self._probe(temporary_output)
                self._validate_joined_output(
                    output_properties,
                    reference_signature,
                    expected_duration,
                )
                self._validate_destination(destination, overwrite=overwrite)
                temporary_output.replace(destination)
        except AudioJoinError:
            raise
        except OSError as error:
            raise AudioJoinError(
                f"Audiodateien konnten nicht nach '{destination}' zusammengeführt werden. "
                "Bitte Zielpfad, Schreibrechte und freien Speicher prüfen."
            ) from error

        LOGGER.info(
            "%d Audiodateien ohne Re-Encoding zu %s zusammengeführt.",
            len(inputs),
            destination,
        )
        return destination

    def _probe(self, path: Path) -> AudioProperties:
        command = [
            self._ffprobe,
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            "stream=codec_name,sample_rate,channels:format=duration",
            "-of",
            "json",
            str(path),
        ]
        completed = self._run(command, "FFprobe")
        if completed.returncode != 0:
            raise AudioJoinError(
                f"Audiodatei '{path}' konnte nicht geprüft werden: "
                f"{completed.stderr.strip() or 'unbekannter FFprobe-Fehler'}"
            )
        try:
            payload: Any = json.loads(completed.stdout)
            stream = payload["streams"][0]
            duration = float(payload["format"]["duration"])
            properties = AudioProperties(
                codec_name=str(stream["codec_name"]),
                sample_rate=int(stream["sample_rate"]),
                channels=int(stream["channels"]),
                duration_seconds=duration,
            )
        except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise AudioJoinError(
                f"FFprobe lieferte für '{path}' keine verwertbaren Audiodaten."
            ) from error
        if properties.duration_seconds <= 0:
            raise AudioJoinError(f"Audiodatei '{path}' besitzt keine positive Dauer.")
        return properties

    def _concatenate(self, manifest: Path, output: Path) -> None:
        command = [
            self._ffmpeg,
            "-hide_banner",
            "-loglevel",
            self._config.log_level,
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(manifest),
            "-map",
            "0:a:0",
            "-c",
            self._config.codec_mode,
            "-map_metadata",
            "-1",
            str(output),
        ]
        completed = self._run(command, "FFmpeg")
        if completed.returncode != 0 or not output.is_file() or output.stat().st_size == 0:
            raise AudioJoinError(
                "FFmpeg konnte die Audiodateien nicht zusammenführen: "
                f"{completed.stderr.strip() or 'keine Ausgabedatei erzeugt'}"
            )

    def _validate_joined_output(
        self,
        properties: AudioProperties,
        expected_signature: tuple[str, int, int],
        expected_duration: float,
    ) -> None:
        if properties.stream_signature != expected_signature:
            raise AudioCompatibilityError(
                "Die zusammengeführte Datei besitzt unerwartete Streamparameter."
            )
        difference = abs(properties.duration_seconds - expected_duration)
        if difference > self._config.duration_tolerance_seconds:
            raise AudioJoinError(
                "Die Dauer der zusammengeführten Datei weicht zu stark von der Summe der "
                f"Eingaben ab ({difference:.3f} Sekunden)."
            )

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
            raise AudioJoinError(
                f"{tool_name} wurde nach {self._config.timeout_seconds:g} Sekunden abgebrochen."
            ) from error
        except OSError as error:
            raise AudioDependencyError(
                f"{tool_name} konnte nicht gestartet werden. Bitte Installation und Pfad prüfen."
            ) from error

    @staticmethod
    def _resolve_executable(
        name: str,
        resolver: ExecutableResolver,
    ) -> str:
        resolved = resolver(name)
        if resolved is None:
            raise AudioDependencyError(
                f"Audio-Werkzeug '{name}' wurde nicht gefunden. Bitte FFmpeg installieren "
                "oder den Pfad in config/audio_joiner.json konfigurieren."
            )
        return resolved

    @staticmethod
    def _build_concat_manifest(paths: tuple[Path, ...]) -> str:
        lines = ["ffconcat version 1.0"]
        for path in paths:
            absolute_path = path.resolve().as_posix()
            escaped_path = absolute_path.replace("'", "'\\''")
            lines.append(f"file '{escaped_path}'")
        return "\n".join(lines) + "\n"

    @staticmethod
    def _validate_destination(destination: Path, *, overwrite: bool) -> None:
        if destination.exists() and not overwrite:
            raise AudioOutputExistsError(
                f"Audio-Ausgabedatei '{destination}' existiert bereits. "
                "Zum Ersetzen ausdrücklich '--overwrite' verwenden."
            )
