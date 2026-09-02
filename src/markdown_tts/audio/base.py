"""Provider-independent contracts for audio postprocessing."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, Sequence


class AudioProcessingError(RuntimeError):
    """Base error for audio postprocessing failures."""


class AudioJoinError(AudioProcessingError):
    """Base error for failed audio joining."""


class AudioDependencyError(AudioJoinError):
    """Raised when a configured audio tool is unavailable."""


class AudioCompatibilityError(AudioJoinError):
    """Raised when input files cannot be joined without re-encoding."""


class AudioOutputExistsError(FileExistsError):
    """Raised before an existing joined audio file would be overwritten."""


class AudioJoiner(Protocol):
    """A replaceable component that combines ordered audio files."""

    def join(
        self,
        input_paths: Sequence[str | Path],
        output_path: str | Path,
        *,
        overwrite: bool = False,
    ) -> Path:
        """Join ordered inputs and return the atomically published output path."""
        ...
