"""Sample-preserving concatenation of compatible PCM WAV files."""

from __future__ import annotations

import logging
import os
from pathlib import Path
import tempfile
from typing import Sequence
import wave

from markdown_tts.audio.base import (
    AudioCompatibilityError,
    AudioJoinError,
    AudioOutputExistsError,
)
from markdown_tts.audio.wav_support import configure_pcm_wav_writer, inspect_wav


LOGGER = logging.getLogger(__name__)


class WavAudioJoiner:
    """Concatenate one or more compatible PCM WAV files without re-encoding."""

    def join(
        self,
        input_paths: Sequence[str | Path],
        output_path: str | Path,
        *,
        overwrite: bool = False,
    ) -> Path:
        inputs = tuple(Path(path) for path in input_paths)
        if not inputs:
            raise AudioJoinError("Zum Zusammenfügen wird mindestens eine WAV-Datei benötigt.")
        for input_path in inputs:
            if not input_path.is_file():
                raise AudioJoinError(f"WAV-Eingabedatei '{input_path}' wurde nicht gefunden.")
            if input_path.suffix.casefold() != ".wav":
                raise AudioCompatibilityError(
                    "Der WAV-Audio-Joiner verarbeitet ausschließlich WAV-Dateien."
                )

        destination = Path(output_path)
        if destination.suffix.casefold() != ".wav":
            raise AudioCompatibilityError("Die zusammengeführte Datei muss auf '.wav' enden.")
        if any(path.resolve() == destination.resolve() for path in inputs):
            raise AudioJoinError("Die Zieldatei darf nicht zugleich Eingabedatei sein.")
        self._validate_destination(destination, overwrite=overwrite)

        properties = tuple(inspect_wav(path) for path in inputs)
        signature = properties[0].stream_signature
        incompatible = next(
            (
                path
                for path, item in zip(inputs, properties, strict=True)
                if item.stream_signature != signature
            ),
            None,
        )
        if incompatible is not None:
            raise AudioCompatibilityError(
                f"WAV-Eingabedatei '{incompatible}' besitzt inkompatible Parameter."
            )
        expected_frames = sum(item.frame_count for item in properties)

        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=f".{destination.stem}-",
                suffix=f"{destination.suffix}.part",
                dir=destination.parent,
            )
            os.close(descriptor)
        except OSError as error:
            raise AudioJoinError(
                f"Temporäre WAV-Datei für '{destination}' konnte nicht angelegt werden."
            ) from error
        temporary_path = Path(temporary_name)
        try:
            with wave.open(str(inputs[0]), "rb") as first, wave.open(
                str(temporary_path), "wb"
            ) as target:
                configure_pcm_wav_writer(target, properties[0])
                for input_path in inputs:
                    with wave.open(str(input_path), "rb") as source:
                        while True:
                            data = source.readframes(65536)
                            if not data:
                                break
                            target.writeframesraw(data)
            combined = inspect_wav(temporary_path)
            if combined.stream_signature != signature or combined.frame_count != expected_frames:
                raise AudioJoinError(
                    "Die zusammengeführte WAV-Datei besitzt unerwartete Parameter oder Länge."
                )
            self._validate_destination(destination, overwrite=overwrite)
            temporary_path.replace(destination)
        except AudioOutputExistsError:
            raise
        except (OSError, EOFError, wave.Error) as error:
            raise AudioJoinError(
                f"WAV-Dateien konnten nicht zu '{destination}' zusammengeführt werden: {error}"
            ) from error
        finally:
            temporary_path.unlink(missing_ok=True)

        LOGGER.info("%d WAV-Datei(en) zu %s zusammengeführt.", len(inputs), destination)
        return destination

    @staticmethod
    def _validate_destination(destination: Path, *, overwrite: bool) -> None:
        if destination.exists() and not overwrite:
            raise AudioOutputExistsError(
                f"Audio-Ausgabedatei '{destination}' existiert bereits. "
                "Zum Ersetzen ausdrücklich '--overwrite' verwenden."
            )
