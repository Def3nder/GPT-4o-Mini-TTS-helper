from __future__ import annotations

from pathlib import Path
import struct
from tempfile import TemporaryDirectory
import unittest
import wave

from markdown_tts.audio import (
    PrefillTrimError,
    WavAudioJoiner,
    WavPrefillTrimmer,
    inspect_wav,
)
from markdown_tts.config import PrefillConfig


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_RATE = 1000


def _write_wav(path: Path, segments: tuple[tuple[int, int], ...]) -> None:
    frames = b"".join(
        struct.pack("<h", amplitude) * frame_count
        for frame_count, amplitude in segments
    )
    with wave.open(str(path), "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(SAMPLE_RATE)
        target.writeframes(frames)


def _mark_wav_sizes_as_streaming_placeholders(path: Path) -> None:
    content = bytearray(path.read_bytes())
    data_marker = content.find(b"data")
    if data_marker < 0:
        raise AssertionError("Test-WAV enthält keinen data-Chunk.")
    struct.pack_into("<I", content, 4, 0xFFFFFFFF)
    struct.pack_into("<I", content, data_marker + 4, 0xFFFFFFFF)
    path.write_bytes(content)


class WavPrefillTrimmerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = PrefillConfig.from_file(PROJECT_ROOT / "config" / "prefill.json")

    def test_cuts_with_safety_margin_inside_nonzero_quiet_region(self) -> None:
        with TemporaryDirectory(dir=PROJECT_ROOT) as directory:
            root = Path(directory)
            source = root / "raw.wav"
            output = root / "trimmed.wav"
            _write_wav(
                source,
                (
                    (400, 12000),
                    (200, 12),
                    (500, 6000),
                ),
            )

            result = WavPrefillTrimmer(self.config).trim(
                source,
                output,
                expected_boundary_seconds=0.5,
            )

            self.assertAlmostEqual(result.quiet_start_seconds, 0.4, places=2)
            self.assertAlmostEqual(result.quiet_end_seconds, 0.6, places=2)
            self.assertAlmostEqual(result.cut_seconds, 0.4, places=2)
            self.assertAlmostEqual(result.output_duration_seconds, 0.7, places=2)
            self.assertEqual(inspect_wav(output).frame_count, 700)

    def test_prefers_last_quiet_region_starting_before_calibrated_boundary(self) -> None:
        with TemporaryDirectory(dir=PROJECT_ROOT) as directory:
            root = Path(directory)
            source = root / "raw.wav"
            output = root / "trimmed.wav"
            _write_wav(
                source,
                (
                    (3650, 12000),
                    (620, 12),
                    (300, 12000),
                    (100, 12),
                    (500, 12000),
                ),
            )

            result = WavPrefillTrimmer(self.config).trim(
                source,
                output,
                expected_boundary_seconds=4.3,
            )

            self.assertAlmostEqual(result.quiet_start_seconds, 3.66, places=2)
            self.assertAlmostEqual(result.quiet_end_seconds, 4.26, places=2)
            self.assertAlmostEqual(result.cut_seconds, 3.81, places=2)

    def test_refuses_to_cut_when_no_quiet_region_exists(self) -> None:
        with TemporaryDirectory(dir=PROJECT_ROOT) as directory:
            root = Path(directory)
            source = root / "raw.wav"
            output = root / "trimmed.wav"
            _write_wav(source, ((1100, 12000),))

            with self.assertRaisesRegex(PrefillTrimError, "energiearme Passage"):
                WavPrefillTrimmer(self.config).trim(
                    source,
                    output,
                    expected_boundary_seconds=0.5,
                )

            self.assertFalse(output.exists())

    def test_uses_actual_pcm_length_for_streaming_wav_placeholder_header(self) -> None:
        with TemporaryDirectory(dir=PROJECT_ROOT) as directory:
            root = Path(directory)
            source = root / "streaming.wav"
            normalized = root / "normalized.wav"
            _write_wav(source, ((625, 1200),))
            _mark_wav_sizes_as_streaming_placeholders(source)

            properties = inspect_wav(source)
            WavAudioJoiner().join((source,), normalized)

            self.assertEqual(properties.frame_count, 625)
            self.assertAlmostEqual(properties.duration_seconds, 0.625)
            self.assertEqual(inspect_wav(normalized).frame_count, 625)

    def test_wav_joiner_preserves_all_pcm_frames(self) -> None:
        with TemporaryDirectory(dir=PROJECT_ROOT) as directory:
            root = Path(directory)
            first = root / "first.wav"
            second = root / "second.wav"
            output = root / "joined.wav"
            _write_wav(first, ((250, 1000),))
            _write_wav(second, ((375, 2000),))

            result = WavAudioJoiner().join((first, second), output)

            self.assertEqual(result, output)
            self.assertEqual(inspect_wav(output).frame_count, 625)


if __name__ == "__main__":
    unittest.main()
