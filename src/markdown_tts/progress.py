"""Provider-independent progress events for synthesis application services."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from markdown_tts.tts.base import SpeechSynthesisResult


@dataclass(frozen=True, slots=True)
class SynthesisProgress:
    """One completed paid synthesis step within a larger operation."""

    stage: str
    current: int
    total: int
    text_characters: int
    result: SpeechSynthesisResult


SynthesisProgressCallback = Callable[[SynthesisProgress], None]
