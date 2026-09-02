"""Replaceable text-to-speech provider interfaces and implementations."""

from markdown_tts.tts.base import (
    SpeechRequest,
    SpeechSynthesisResult,
    SpeechUsage,
    TTSProvider,
)
from markdown_tts.tts.factory import UnsupportedTTSProviderError, create_tts_provider
from markdown_tts.tts.openai_provider import (
    MissingApiKeyError,
    OpenAITTSProvider,
    OutputFileExistsError,
    TTSGenerationError,
)

__all__ = [
    "MissingApiKeyError",
    "OpenAITTSProvider",
    "OutputFileExistsError",
    "SpeechRequest",
    "SpeechSynthesisResult",
    "SpeechUsage",
    "TTSGenerationError",
    "TTSProvider",
    "UnsupportedTTSProviderError",
    "create_tts_provider",
]
