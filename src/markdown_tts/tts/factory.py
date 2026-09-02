"""TTS provider selection without leaking provider logic into callers."""

from __future__ import annotations

from typing import Mapping

from markdown_tts.config import TTSProviderConfig
from markdown_tts.tts.base import TTSProvider
from markdown_tts.tts.openai_provider import OpenAITTSProvider


class UnsupportedTTSProviderError(ValueError):
    """Raised when configuration requests an unavailable provider."""


def create_tts_provider(
    config: TTSProviderConfig,
    *,
    environment: Mapping[str, str] | None = None,
) -> TTSProvider:
    """Create the configured provider behind the shared protocol."""
    if config.provider.casefold() == "openai":
        return OpenAITTSProvider(config, environment=environment)
    raise UnsupportedTTSProviderError(
        f"TTS-Provider '{config.provider}' wird nicht unterstützt. Verfügbar: openai."
    )
