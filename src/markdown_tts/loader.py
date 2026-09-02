"""File loading concerns for Markdown input."""

from __future__ import annotations

import logging
from pathlib import Path


LOGGER = logging.getLogger(__name__)


class MarkdownLoadError(ValueError):
    """Raised when a Markdown source cannot be loaded safely."""


def load_markdown(path: str | Path) -> str:
    """Load a Markdown file as strict UTF-8, accepting an optional UTF-8 BOM."""
    markdown_path = Path(path)
    LOGGER.info("Lade Markdown-Datei: %s", markdown_path)
    try:
        content = markdown_path.read_bytes()
    except OSError as error:
        raise MarkdownLoadError(
            f"Markdown-Datei '{markdown_path}' konnte nicht gelesen werden. "
            "Bitte Pfad und Zugriffsrechte prüfen."
        ) from error

    try:
        return content.decode("utf-8-sig", errors="strict")
    except UnicodeDecodeError as error:
        raise MarkdownLoadError(
            f"Markdown-Datei '{markdown_path}' ist nicht gültig UTF-8. "
            "Bitte die Datei als UTF-8 speichern und erneut versuchen."
        ) from error
