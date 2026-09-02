"""Remove a synthesized prefill at the midpoint of a nearby quiet WAV region."""

from __future__ import annotations

from dataclasses import dataclass
import logging
import math
import os
from pathlib import Path
import tempfile
import wave

from markdown_tts.audio.base import AudioOutputExistsError, AudioProcessingError
from markdown_tts.audio.wav_support import (
    WavProperties,
    configure_pcm_wav_writer,
    inspect_wav,
)
from markdown_tts.config import PrefillConfig


LOGGER = logging.getLogger(__name__)


class PrefillTrimError(AudioProcessingError):
    """Raised when no safe prefill boundary can be identified or published."""


@dataclass(frozen=True, slots=True)
class QuietRegion:
    start_frame: int
    end_frame: int

    @property
    def midpoint_frame(self) -> int:
        return (self.start_frame + self.end_frame) // 2


@dataclass(frozen=True, slots=True)
class PrefillTrimResult:
    output_path: Path
    source_duration_seconds: float
    cut_seconds: float
    quiet_start_seconds: float
    quiet_end_seconds: float
    output_duration_seconds: float


class WavPrefillTrimmer:
    """Find low-energy PCM windows near calibration duration and trim atomically."""

    def __init__(self, config: PrefillConfig) -> None:
        self._config = config

    def trim(
        self,
        input_path: str | Path,
        output_path: str | Path,
        *,
        expected_boundary_seconds: float,
        overwrite: bool = False,
    ) -> PrefillTrimResult:
        """Remove audio before the midpoint of the best nearby quiet region."""
        source_path = Path(input_path)
        destination = Path(output_path)
        if expected_boundary_seconds <= 0:
            raise PrefillTrimError("Die erwartete Prefill-Grenze muss positiv sein.")
        if destination.exists() and not overwrite:
            raise AudioOutputExistsError(
                f"Audio-Ausgabedatei '{destination}' existiert bereits."
            )
        if source_path.suffix.casefold() != ".wav" or destination.suffix.casefold() != ".wav":
            raise PrefillTrimError("Der Prefill-Trimmer verarbeitet ausschließlich WAV-Dateien.")

        properties = inspect_wav(source_path)
        quiet_region = self._find_quiet_region(
            source_path,
            properties,
            expected_boundary_seconds,
        )
        safety_frames = round(
            self._config.cut_safety_seconds * properties.sample_rate
        )
        cut_frame = max(
            quiet_region.start_frame,
            quiet_region.midpoint_frame - safety_frames,
        )
        remaining_frames = properties.frame_count - cut_frame
        minimum_remaining_frames = math.ceil(
            self._config.minimum_remaining_seconds * properties.sample_rate
        )
        if remaining_frames < minimum_remaining_frames:
            raise PrefillTrimError(
                "Nach der erkannten Prefill-Grenze verbleibt zu wenig Nutzsignal."
            )

        self._write_trimmed_wav(
            source_path,
            destination,
            cut_frame,
            properties,
            overwrite=overwrite,
        )
        output_properties = inspect_wav(destination)
        expected_frames = remaining_frames
        if output_properties.stream_signature != properties.stream_signature:
            destination.unlink(missing_ok=True)
            raise PrefillTrimError("Die getrimmte WAV-Datei besitzt unerwartete Parameter.")
        if output_properties.frame_count != expected_frames:
            destination.unlink(missing_ok=True)
            raise PrefillTrimError("Die getrimmte WAV-Datei besitzt eine unerwartete Länge.")

        result = PrefillTrimResult(
            output_path=destination,
            source_duration_seconds=properties.duration_seconds,
            cut_seconds=cut_frame / properties.sample_rate,
            quiet_start_seconds=quiet_region.start_frame / properties.sample_rate,
            quiet_end_seconds=quiet_region.end_frame / properties.sample_rate,
            output_duration_seconds=output_properties.duration_seconds,
        )
        LOGGER.info(
            "Prefill aus %s bei %.3f Sekunden entfernt; erkannte Ruhephase %.3f–%.3f.",
            source_path,
            result.cut_seconds,
            result.quiet_start_seconds,
            result.quiet_end_seconds,
        )
        return result

    def _find_quiet_region(
        self,
        path: Path,
        properties: WavProperties,
        expected_seconds: float,
    ) -> QuietRegion:
        search_start = max(
            0,
            math.floor(
                (expected_seconds - self._config.search_before_seconds)
                * properties.sample_rate
            ),
        )
        search_end = min(
            properties.frame_count,
            math.ceil(
                (expected_seconds + self._config.search_after_seconds)
                * properties.sample_rate
            ),
        )
        if search_end <= search_start:
            raise PrefillTrimError("Das konfigurierte Prefill-Suchfenster ist leer.")

        window_frames = max(
            1,
            round(
                self._config.analysis_window_milliseconds
                * properties.sample_rate
                / 1000
            ),
        )
        minimum_quiet_frames = max(
            1,
            math.ceil(
                self._config.minimum_quiet_milliseconds
                * properties.sample_rate
                / 1000
            ),
        )
        windows: list[tuple[int, int, float]] = []
        try:
            with wave.open(str(path), "rb") as source:
                source.setpos(search_start)
                position = search_start
                while position < search_end:
                    frame_count = min(window_frames, search_end - position)
                    data = source.readframes(frame_count)
                    if not data:
                        break
                    actual_frames = len(data) // (
                        properties.channels * properties.sample_width_bytes
                    )
                    end = position + actual_frames
                    windows.append(
                        (
                            position,
                            end,
                            _dbfs(data, properties.sample_width_bytes),
                        )
                    )
                    position = end
        except (OSError, EOFError, wave.Error) as error:
            raise PrefillTrimError(
                f"WAV-Datei '{path}' konnte nicht analysiert werden: {error}"
            ) from error

        regions: list[QuietRegion] = []
        active_start: int | None = None
        active_end = 0
        for start, end, level_dbfs in windows:
            if level_dbfs <= self._config.quiet_threshold_dbfs:
                if active_start is None:
                    active_start = start
                active_end = end
                continue
            if active_start is not None and active_end - active_start >= minimum_quiet_frames:
                regions.append(QuietRegion(active_start, active_end))
            active_start = None
        if active_start is not None and active_end - active_start >= minimum_quiet_frames:
            regions.append(QuietRegion(active_start, active_end))

        if not regions:
            raise PrefillTrimError(
                "Im erwarteten Bereich wurde keine ausreichend lange energiearme Passage "
                f"unter {self._config.quiet_threshold_dbfs:g} dBFS gefunden. "
                "Bitte Kalibrierung oder Prefill-Konfiguration prüfen."
            )
        expected_frame = round(expected_seconds * properties.sample_rate)
        safe_regions = [
            region for region in regions if region.start_frame <= expected_frame
        ]
        if not safe_regions:
            raise PrefillTrimError(
                "Vor der kalibrierten Prefill-Grenze wurde keine ausreichend lange "
                "energiearme Passage gefunden. Der Nutztext wird aus Sicherheitsgründen "
                "nicht angeschnitten."
            )
        return max(safe_regions, key=lambda region: region.start_frame)

    @staticmethod
    def _write_trimmed_wav(
        source_path: Path,
        destination: Path,
        cut_frame: int,
        properties: WavProperties,
        *,
        overwrite: bool,
    ) -> None:
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=f".{destination.stem}-",
                suffix=f"{destination.suffix}.part",
                dir=destination.parent,
            )
            os.close(descriptor)
        except OSError as error:
            raise PrefillTrimError(
                f"Temporäre WAV-Datei für '{destination}' konnte nicht angelegt werden."
            ) from error
        temporary_path = Path(temporary_name)
        try:
            with wave.open(str(source_path), "rb") as source, wave.open(
                str(temporary_path), "wb"
            ) as target:
                configure_pcm_wav_writer(target, properties)
                source.setpos(cut_frame)
                while True:
                    data = source.readframes(65536)
                    if not data:
                        break
                    target.writeframesraw(data)
            if destination.exists() and not overwrite:
                raise AudioOutputExistsError(
                    f"Audio-Ausgabedatei '{destination}' wurde zwischenzeitlich angelegt."
                )
            temporary_path.replace(destination)
        except AudioOutputExistsError:
            raise
        except (OSError, EOFError, wave.Error) as error:
            raise PrefillTrimError(
                f"Getrimmte WAV-Datei '{destination}' konnte nicht geschrieben werden: {error}"
            ) from error
        finally:
            temporary_path.unlink(missing_ok=True)


def _dbfs(data: bytes, sample_width_bytes: int) -> float:
    samples = _decode_pcm_samples(data, sample_width_bytes)
    if not samples:
        return float("-inf")
    mean_square = sum(sample * sample for sample in samples) / len(samples)
    if mean_square <= 0:
        return float("-inf")
    full_scale = (1 << (8 * sample_width_bytes - 1)) - 1
    return 20 * math.log10(math.sqrt(mean_square) / full_scale)


def _decode_pcm_samples(data: bytes, sample_width_bytes: int) -> tuple[int, ...]:
    if sample_width_bytes == 1:
        return tuple(value - 128 for value in data)
    return tuple(
        int.from_bytes(
            data[index : index + sample_width_bytes],
            byteorder="little",
            signed=True,
        )
        for index in range(0, len(data), sample_width_bytes)
    )
