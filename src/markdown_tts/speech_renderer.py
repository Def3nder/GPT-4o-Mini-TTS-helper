"""Translate semantic speech blocks into a provider request."""

from __future__ import annotations

from markdown_tts.config import SpeechProfile
from markdown_tts.semantic_renderer import SpeechDocument
from markdown_tts.tts.base import SpeechRequest


class EmptySpeechDocumentError(ValueError):
    """Raised when a document contains no speakable content."""


class SpeechRenderer:
    """Build a provider request with one global speech profile."""

    def __init__(self, profile: SpeechProfile) -> None:
        self._profile = profile

    def render(self, document: SpeechDocument) -> SpeechRequest:
        """Create one provider-neutral request for a single speech chunk."""
        if not document.text.strip():
            raise EmptySpeechDocumentError(
                "Das Dokument enthält nach der semantischen Bereinigung keinen sprechbaren Text."
            )

        return SpeechRequest(
            text=document.text,
            voice=self._profile.voice,
            instructions=self._profile.instructions.strip(),
            speed=self._profile.speed,
        )
