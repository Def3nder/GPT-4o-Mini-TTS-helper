"""Discovery and selection of JSON-backed speech profiles."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from markdown_tts.config import ConfigurationError, SpeechProfile


class SpeechProfileCatalogError(ConfigurationError):
    """Raised when profiles cannot be discovered or selected unambiguously."""


@dataclass(frozen=True, slots=True)
class SpeechProfileEntry:
    """One discoverable profile together with its source file."""

    path: Path
    profile: SpeechProfile


class SpeechProfileCatalog:
    """Discover configured profiles and resolve names without provider coupling."""

    def __init__(self, directory: str | Path) -> None:
        self._directory = Path(directory)

    def list_entries(self) -> tuple[SpeechProfileEntry, ...]:
        """Load all JSON profiles in deterministic name order."""
        if not self._directory.is_dir():
            raise SpeechProfileCatalogError(
                f"Sprachprofil-Verzeichnis '{self._directory}' wurde nicht gefunden."
            )

        entries = tuple(
            sorted(
                (
                    SpeechProfileEntry(path=path, profile=SpeechProfile.from_file(path))
                    for path in self._directory.glob("*.json")
                ),
                key=lambda entry: (
                    entry.profile.name.casefold(),
                    entry.path.name.casefold(),
                ),
            )
        )
        if not entries:
            raise SpeechProfileCatalogError(
                f"Im Verzeichnis '{self._directory}' wurden keine JSON-Sprachprofile gefunden."
            )

        seen_names: dict[str, Path] = {}
        for entry in entries:
            normalized_name = entry.profile.name.casefold()
            previous_path = seen_names.get(normalized_name)
            if previous_path is not None:
                raise SpeechProfileCatalogError(
                    f"Sprachprofilname '{entry.profile.name}' ist mehrfach definiert: "
                    f"'{previous_path}' und '{entry.path}'."
                )
            seen_names[normalized_name] = entry.path
        return entries

    def resolve(self, reference: str | Path) -> SpeechProfile:
        """Resolve a catalog name, file stem, or explicit JSON file path."""
        raw_reference = str(reference).strip()
        if not raw_reference:
            raise SpeechProfileCatalogError("Sprachprofil darf nicht leer sein.")

        explicit_path = Path(raw_reference)
        if explicit_path.is_file():
            return SpeechProfile.from_file(explicit_path)

        normalized_reference = raw_reference.casefold()
        entries = self.list_entries()
        for entry in entries:
            if normalized_reference in {
                entry.profile.name.casefold(),
                entry.path.stem.casefold(),
            }:
                return entry.profile

        available = ", ".join(entry.profile.name for entry in entries)
        raise SpeechProfileCatalogError(
            f"Sprachprofil '{reference}' wurde nicht gefunden. Verfügbar: {available}."
        )
