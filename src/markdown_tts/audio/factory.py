"""Audio-joiner selection without leaking implementation details upstream."""

from __future__ import annotations

from markdown_tts.audio.base import AudioJoiner
from markdown_tts.audio.ffmpeg_joiner import FFmpegAudioJoiner
from markdown_tts.config import AudioJoinerConfig


class UnsupportedAudioJoinerError(ValueError):
    """Raised when configuration requests an unavailable audio backend."""


def create_audio_joiner(config: AudioJoinerConfig) -> AudioJoiner:
    """Create the configured audio joiner behind the shared protocol."""
    if config.backend.casefold() == "ffmpeg":
        return FFmpegAudioJoiner(config)
    raise UnsupportedAudioJoinerError(
        f"Audio-Joiner '{config.backend}' wird nicht unterstützt. Verfügbar: ffmpeg."
    )
