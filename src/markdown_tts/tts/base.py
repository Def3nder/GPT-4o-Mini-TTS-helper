"""Provider-independent TTS contracts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True, slots=True)
class SpeechRequest:
    text: str
    voice: str
    instructions: str
    speed: float = 1.0


@dataclass(frozen=True, slots=True)
class SpeechUsage:
    """Actual token usage reported by a speech provider for one request."""

    input_tokens: int
    output_tokens: int
    total_tokens: int


@dataclass(frozen=True, slots=True)
class SpeechSynthesisResult:
    """Published audio path and optional provider-reported usage."""

    output_path: Path
    usage: SpeechUsage | None = None


class TTSProvider(Protocol):
    """A replaceable text-to-speech provider."""

    def synthesize(
        self,
        request: SpeechRequest,
        output_path: str | Path,
        *,
        overwrite: bool = False,
    ) -> SpeechSynthesisResult:
        """Generate one audio file and return its path plus reported usage."""
        ...
