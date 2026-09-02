"""Shared inspection helpers for uncompressed PCM WAV files."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from pathlib import Path
import wave

from markdown_tts.audio.base import AudioProcessingError


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class WavProperties:
    channels: int
    sample_width_bytes: int
    sample_rate: int
    frame_count: int
    compression_type: str

    @property
    def duration_seconds(self) -> float:
        return self.frame_count / self.sample_rate

    @property
    def stream_signature(self) -> tuple[int, int, int, str]:
        return (
            self.channels,
            self.sample_width_bytes,
            self.sample_rate,
            self.compression_type,
        )


def inspect_wav(path: str | Path) -> WavProperties:
    """Return validated PCM WAV properties."""
    wav_path = Path(path)
    try:
        with wave.open(str(wav_path), "rb") as source:
            channels = source.getnchannels()
            sample_width_bytes = source.getsampwidth()
            declared_frame_count = source.getnframes()
            bytes_per_frame = channels * sample_width_bytes
            frame_count = declared_frame_count
            if declared_frame_count * bytes_per_frame > wav_path.stat().st_size:
                frame_count = _count_readable_frames(source, bytes_per_frame)
                LOGGER.warning(
                    "WAV-Header von %s enthält eine Streaming-Platzhalterlänge; "
                    "%d tatsächlich lesbare Frames werden verwendet.",
                    wav_path,
                    frame_count,
                )
            properties = WavProperties(
                channels=channels,
                sample_width_bytes=sample_width_bytes,
                sample_rate=source.getframerate(),
                frame_count=frame_count,
                compression_type=source.getcomptype(),
            )
    except (OSError, EOFError, wave.Error) as error:
        raise AudioProcessingError(
            f"WAV-Datei '{wav_path}' konnte nicht gelesen werden: {error}"
        ) from error
    if properties.compression_type != "NONE":
        raise AudioProcessingError(
            f"WAV-Datei '{wav_path}' verwendet keine unkomprimierten PCM-Daten."
        )
    if min(
        properties.channels,
        properties.sample_width_bytes,
        properties.sample_rate,
        properties.frame_count,
    ) <= 0:
        raise AudioProcessingError(f"WAV-Datei '{wav_path}' besitzt ungültige Parameter.")
    if properties.sample_width_bytes not in {1, 2, 3, 4}:
        raise AudioProcessingError(
            f"WAV-Datei '{wav_path}' verwendet eine nicht unterstützte Samplebreite von "
            f"{properties.sample_width_bytes} Byte."
        )
    return properties


def configure_pcm_wav_writer(
    target: wave.Wave_write,
    properties: WavProperties,
) -> None:
    """Configure a WAV writer without copying a possibly invalid frame count."""
    target.setnchannels(properties.channels)
    target.setsampwidth(properties.sample_width_bytes)
    target.setframerate(properties.sample_rate)
    target.setcomptype("NONE", "not compressed")


def _count_readable_frames(source: wave.Wave_read, bytes_per_frame: int) -> int:
    source.rewind()
    readable_bytes = 0
    while True:
        data = source.readframes(65536)
        if not data:
            break
        readable_bytes += len(data)
    if readable_bytes % bytes_per_frame != 0:
        raise AudioProcessingError(
            "WAV-Nutzdaten enden nicht an einer vollständigen PCM-Framegrenze."
        )
    return readable_bytes // bytes_per_frame
