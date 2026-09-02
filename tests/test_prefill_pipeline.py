from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import struct
from tempfile import TemporaryDirectory
import unittest
import wave

from markdown_tts.application import PrefillCalibrator, PrefillMarkdownAudioConverter
from markdown_tts.audio import (
    PrefillTrimError,
    WavAudioJoiner,
    WavPrefillTrimmer,
    inspect_wav,
)
from markdown_tts.chunker import SemanticChunker
from markdown_tts.config import (
    ChunkingRules,
    ParserRules,
    PrefillConfig,
    SemanticRendererRules,
    SpeechProfile,
    TTSProviderConfig,
)
from markdown_tts.loader import MarkdownLoadError
from markdown_tts.parser import MarkdownParser
from markdown_tts.prefill import (
    PrefillCalibration,
    PrefillCalibrationError,
    prefill_calibration_cache_path,
    prefill_configuration_fingerprint,
)
from markdown_tts.semantic_renderer import SemanticRenderer
from markdown_tts.speech_renderer import SpeechRenderer
from markdown_tts.tts.base import SpeechRequest, SpeechSynthesisResult


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_RATE = 1000


def _write_test_wav(path: Path, segments: tuple[tuple[int, int], ...]) -> None:
    frames = b"".join(
        struct.pack("<h", amplitude) * frame_count
        for frame_count, amplitude in segments
    )
    with wave.open(str(path), "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(SAMPLE_RATE)
        target.writeframes(frames)


class _SyntheticWavProvider:
    def __init__(self, prefill_text: str, *, include_quiet_region: bool = True) -> None:
        self.prefill_text = prefill_text
        self.include_quiet_region = include_quiet_region
        self.requests: list[SpeechRequest] = []

    def synthesize(
        self,
        request: SpeechRequest,
        output_path: str | Path,
        *,
        overwrite: bool = False,
    ) -> SpeechSynthesisResult:
        self.requests.append(request)
        output = Path(output_path)
        if request.text == self.prefill_text:
            _write_test_wav(output, ((500, 8000),))
        elif self.include_quiet_region:
            _write_test_wav(output, ((400, 10000), (200, 10), (500, 6000)))
        else:
            _write_test_wav(output, ((1100, 10000),))
        return SpeechSynthesisResult(output)


class _CapturingEncoder:
    def __init__(self) -> None:
        self.source_frames: int | None = None
        self.calls = 0

    def encode(
        self,
        input_path: str | Path,
        output_path: str | Path,
        *,
        overwrite: bool = False,
    ) -> Path:
        self.calls += 1
        self.source_frames = inspect_wav(input_path).frame_count
        destination = Path(output_path)
        destination.write_bytes(b"ID3-prefill-result")
        return destination


class PrefillPipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.prefill_config = PrefillConfig.from_file(
            PROJECT_ROOT / "config" / "prefill.json"
        )
        cls.provider_config = TTSProviderConfig.from_file(
            PROJECT_ROOT / "config" / "tts_provider_wav.json"
        )
        cls.profile = SpeechProfile.from_file(
            PROJECT_ROOT / "speech_profiles" / "coaching.json"
        )

    @staticmethod
    def _parser() -> MarkdownParser:
        return MarkdownParser(
            ParserRules.from_file(PROJECT_ROOT / "config" / "parser_rules.json")
        )

    @staticmethod
    def _semantic_renderer() -> SemanticRenderer:
        return SemanticRenderer(
            SemanticRendererRules.from_file(
                PROJECT_ROOT / "config" / "semantic_renderer.json"
            )
        )

    def _calibration(self) -> PrefillCalibration:
        return PrefillCalibration.create(
            self.prefill_config,
            self.profile,
            self.provider_config,
            duration_seconds=0.5,
            sample_rate=SAMPLE_RATE,
            channels=1,
            sample_width_bytes=2,
        )

    def test_calibrator_measures_wav_and_publishes_bound_json(self) -> None:
        provider = _SyntheticWavProvider(self.prefill_config.text)
        calibrator = PrefillCalibrator(
            SpeechRenderer(self.profile),
            provider,
            self.prefill_config,
            self.profile,
            self.provider_config,
        )
        with TemporaryDirectory(dir=PROJECT_ROOT) as directory:
            output = Path(directory) / "calibration.json"

            calibration = calibrator.calibrate(output)
            loaded = PrefillCalibration.from_file(output)

            self.assertEqual(len(provider.requests), 1)
            self.assertEqual(provider.requests[0].text, self.prefill_config.text)
            self.assertAlmostEqual(calibration.duration_seconds, 0.5)
            self.assertEqual(loaded, calibration)
            calibration_audio = output.with_suffix(".wav")
            self.assertTrue(calibration_audio.is_file())
            self.assertEqual(inspect_wav(calibration_audio).frame_count, 500)

    def test_fingerprint_covers_effective_instructions_and_prefill_separator(self) -> None:
        original = prefill_configuration_fingerprint(
            self.prefill_config,
            self.profile,
            self.provider_config,
        )
        changed_instructions = prefill_configuration_fingerprint(
            self.prefill_config,
            replace(self.profile, instructions="Andere globale Anweisungen."),
            self.provider_config,
        )
        changed_separator = prefill_configuration_fingerprint(
            replace(self.prefill_config, separator="\n"),
            self.profile,
            self.provider_config,
        )

        self.assertNotEqual(original, changed_instructions)
        self.assertNotEqual(original, changed_separator)

    def test_calibrator_reuses_matching_cache_and_refreshes_only_on_request(self) -> None:
        provider = _SyntheticWavProvider(self.prefill_config.text)
        calibrator = PrefillCalibrator(
            SpeechRenderer(self.profile),
            provider,
            self.prefill_config,
            self.profile,
            self.provider_config,
        )
        with TemporaryDirectory(dir=PROJECT_ROOT) as directory:
            cache_directory = Path(directory) / "cache"

            first = calibrator.resolve(cache_directory)
            cached = calibrator.resolve(cache_directory)
            refreshed = calibrator.resolve(cache_directory, refresh=True)

            expected_path = prefill_calibration_cache_path(
                cache_directory,
                self.prefill_config,
                self.profile,
                self.provider_config,
            )
            self.assertEqual(first.path, expected_path)
            self.assertEqual(first.audio_path, expected_path.with_suffix(".wav"))
            self.assertTrue(first.audio_path.is_file())
            self.assertTrue(first.created)
            self.assertFalse(cached.created)
            self.assertTrue(refreshed.created)
            self.assertEqual(len(provider.requests), 2)
            self.assertEqual(
                first.calibration.configuration_sha256,
                cached.calibration.configuration_sha256,
            )

    def test_prefill_pipeline_reserves_input_trims_each_chunk_and_publishes_once(self) -> None:
        provider = _SyntheticWavProvider(self.prefill_config.text)
        encoder = _CapturingEncoder()
        rules = replace(
            ChunkingRules.from_file(PROJECT_ROOT / "config" / "chunking.json"),
            max_characters=150,
            preferred_minimum_characters=40,
        )
        chunker = SemanticChunker(
            rules,
            reserved_characters=self.prefill_config.reserved_characters,
        )
        converter = PrefillMarkdownAudioConverter(
            self._parser(),
            self._semantic_renderer(),
            chunker,
            SpeechRenderer(self.profile),
            provider,
            self.provider_config,
            self.profile,
            self.prefill_config,
            WavPrefillTrimmer(self.prefill_config),
            WavAudioJoiner(),
            encoder,
        )

        with TemporaryDirectory(dir=PROJECT_ROOT) as directory:
            root = Path(directory)
            source = root / "article.md"
            source.write_text(
                " ".join(
                    f"Dies ist der vollständige Testsatz Nummer {number}."
                    for number in range(1, 9)
                ),
                encoding="utf-8",
            )
            output = root / "final.mp3"

            result = converter.convert(source, output, self._calibration())

            self.assertEqual(result.read_bytes(), b"ID3-prefill-result")
            self.assertGreater(len(provider.requests), 1)
            self.assertTrue(
                all(
                    request.text.startswith(self.prefill_config.request_prefix)
                    for request in provider.requests
                )
            )
            self.assertTrue(all(len(request.text) <= 150 for request in provider.requests))
            self.assertEqual(encoder.calls, 1)
            self.assertEqual(encoder.source_frames, 700 * len(provider.requests))
            self.assertEqual(list(root.glob(".*-prefill-*")), [])

    def test_rejects_stale_calibration_before_provider_call(self) -> None:
        provider = _SyntheticWavProvider(self.prefill_config.text)
        encoder = _CapturingEncoder()
        rules = ChunkingRules.from_file(PROJECT_ROOT / "config" / "chunking.json")
        converter = PrefillMarkdownAudioConverter(
            self._parser(),
            self._semantic_renderer(),
            SemanticChunker(
                rules,
                reserved_characters=self.prefill_config.reserved_characters,
            ),
            SpeechRenderer(self.profile),
            provider,
            self.provider_config,
            self.profile,
            self.prefill_config,
            WavPrefillTrimmer(self.prefill_config),
            WavAudioJoiner(),
            encoder,
        )
        stale = replace(self._calibration(), model="anderes-modell")

        with TemporaryDirectory(dir=PROJECT_ROOT) as directory:
            root = Path(directory)
            source = root / "article.md"
            source.write_text("Ein kurzer Testsatz.", encoding="utf-8")

            with self.assertRaisesRegex(PrefillCalibrationError, "neu kalibrieren"):
                converter.convert(source, root / "final.mp3", stale)

            self.assertEqual(provider.requests, [])
            self.assertEqual(encoder.calls, 0)

    def test_does_not_publish_when_chunk_has_no_safe_quiet_region(self) -> None:
        provider = _SyntheticWavProvider(
            self.prefill_config.text,
            include_quiet_region=False,
        )
        encoder = _CapturingEncoder()
        rules = ChunkingRules.from_file(PROJECT_ROOT / "config" / "chunking.json")
        converter = PrefillMarkdownAudioConverter(
            self._parser(),
            self._semantic_renderer(),
            SemanticChunker(
                rules,
                reserved_characters=self.prefill_config.reserved_characters,
            ),
            SpeechRenderer(self.profile),
            provider,
            self.provider_config,
            self.profile,
            self.prefill_config,
            WavPrefillTrimmer(self.prefill_config),
            WavAudioJoiner(),
            encoder,
        )

        with TemporaryDirectory(dir=PROJECT_ROOT) as directory:
            root = Path(directory)
            source = root / "article.md"
            source.write_text("Ein kurzer vollständiger Testsatz.", encoding="utf-8")
            output = root / "final.mp3"

            with self.assertRaises(PrefillTrimError):
                converter.convert(source, output, self._calibration())

            self.assertFalse(output.exists())
            self.assertEqual(encoder.calls, 0)
            retained = list(root.glob(".final-prefill-*"))
            self.assertEqual(len(retained), 1)
            self.assertTrue((retained[0] / "raw-001.wav").is_file())

    def test_existing_output_prevents_automatic_calibration_call(self) -> None:
        provider = _SyntheticWavProvider(self.prefill_config.text)
        encoder = _CapturingEncoder()
        rules = ChunkingRules.from_file(PROJECT_ROOT / "config" / "chunking.json")
        converter = PrefillMarkdownAudioConverter(
            self._parser(),
            self._semantic_renderer(),
            SemanticChunker(
                rules,
                reserved_characters=self.prefill_config.reserved_characters,
            ),
            SpeechRenderer(self.profile),
            provider,
            self.provider_config,
            self.profile,
            self.prefill_config,
            WavPrefillTrimmer(self.prefill_config),
            WavAudioJoiner(),
            encoder,
        )
        calibrator = PrefillCalibrator(
            SpeechRenderer(self.profile),
            provider,
            self.prefill_config,
            self.profile,
            self.provider_config,
        )

        with TemporaryDirectory(dir=PROJECT_ROOT) as directory:
            root = Path(directory)
            source = root / "article.md"
            source.write_text("Ein kurzer vollständiger Testsatz.", encoding="utf-8")
            output = root / "final.mp3"
            output.write_bytes(b"existing")

            with self.assertRaises(FileExistsError):
                converter.convert_with_cached_calibration(
                    source,
                    output,
                    calibrator,
                    root / "cache",
                )

            self.assertEqual(provider.requests, [])
            self.assertEqual(output.read_bytes(), b"existing")

    def test_keeps_new_calibration_when_later_chunk_trimming_fails(self) -> None:
        provider = _SyntheticWavProvider(
            self.prefill_config.text,
            include_quiet_region=False,
        )
        encoder = _CapturingEncoder()
        rules = ChunkingRules.from_file(PROJECT_ROOT / "config" / "chunking.json")
        converter = PrefillMarkdownAudioConverter(
            self._parser(),
            self._semantic_renderer(),
            SemanticChunker(
                rules,
                reserved_characters=self.prefill_config.reserved_characters,
            ),
            SpeechRenderer(self.profile),
            provider,
            self.provider_config,
            self.profile,
            self.prefill_config,
            WavPrefillTrimmer(self.prefill_config),
            WavAudioJoiner(),
            encoder,
        )
        calibrator = PrefillCalibrator(
            SpeechRenderer(self.profile),
            provider,
            self.prefill_config,
            self.profile,
            self.provider_config,
        )

        with TemporaryDirectory(dir=PROJECT_ROOT) as directory:
            root = Path(directory)
            source = root / "article.md"
            source.write_text("Ein kurzer vollständiger Testsatz.", encoding="utf-8")
            output = root / "final.mp3"
            cache = root / "cache"

            with self.assertRaises(PrefillTrimError):
                converter.convert_with_cached_calibration(
                    source,
                    output,
                    calibrator,
                    cache,
                )

            calibration_path = prefill_calibration_cache_path(
                cache,
                self.prefill_config,
                self.profile,
                self.provider_config,
            )
            self.assertTrue(calibration_path.is_file())
            self.assertTrue(calibration_path.with_suffix(".wav").is_file())
            self.assertFalse(output.exists())
            self.assertEqual(len(provider.requests), 2)

    def test_automatic_pipeline_creates_then_reuses_cached_calibration(self) -> None:
        provider = _SyntheticWavProvider(self.prefill_config.text)
        encoder = _CapturingEncoder()
        rules = ChunkingRules.from_file(PROJECT_ROOT / "config" / "chunking.json")
        converter = PrefillMarkdownAudioConverter(
            self._parser(),
            self._semantic_renderer(),
            SemanticChunker(
                rules,
                reserved_characters=self.prefill_config.reserved_characters,
            ),
            SpeechRenderer(self.profile),
            provider,
            self.provider_config,
            self.profile,
            self.prefill_config,
            WavPrefillTrimmer(self.prefill_config),
            WavAudioJoiner(),
            encoder,
        )
        calibrator = PrefillCalibrator(
            SpeechRenderer(self.profile),
            provider,
            self.prefill_config,
            self.profile,
            self.provider_config,
        )

        with TemporaryDirectory(dir=PROJECT_ROOT) as directory:
            root = Path(directory)
            source = root / "article.md"
            source.write_text("Ein kurzer vollständiger Testsatz.", encoding="utf-8")
            cache = root / "cache"

            first = converter.convert_with_cached_calibration(
                source,
                root / "first.mp3",
                calibrator,
                cache,
            )
            second = converter.convert_with_cached_calibration(
                source,
                root / "second.mp3",
                calibrator,
                cache,
            )

            self.assertTrue(first.calibration_created)
            self.assertFalse(second.calibration_created)
            self.assertEqual(first.calibration_path, second.calibration_path)
            self.assertTrue(first.calibration_path.is_file())
            self.assertEqual(
                first.calibration_audio_path,
                second.calibration_audio_path,
            )
            self.assertTrue(first.calibration_audio_path.is_file())
            self.assertEqual(first.output_path.read_bytes(), b"ID3-prefill-result")
            self.assertEqual(second.output_path.read_bytes(), b"ID3-prefill-result")
            self.assertEqual(len(provider.requests), 3)
            self.assertEqual(encoder.calls, 2)

    def test_keep_chunks_preserves_raw_trimmed_and_combined_wav_after_success(self) -> None:
        provider = _SyntheticWavProvider(self.prefill_config.text)
        encoder = _CapturingEncoder()
        rules = ChunkingRules.from_file(PROJECT_ROOT / "config" / "chunking.json")
        converter = PrefillMarkdownAudioConverter(
            self._parser(),
            self._semantic_renderer(),
            SemanticChunker(
                rules,
                reserved_characters=self.prefill_config.reserved_characters,
            ),
            SpeechRenderer(self.profile),
            provider,
            self.provider_config,
            self.profile,
            self.prefill_config,
            WavPrefillTrimmer(self.prefill_config),
            WavAudioJoiner(),
            encoder,
        )
        calibrator = PrefillCalibrator(
            SpeechRenderer(self.profile),
            provider,
            self.prefill_config,
            self.profile,
            self.provider_config,
        )

        with TemporaryDirectory(dir=PROJECT_ROOT) as directory:
            root = Path(directory)
            source = root / "article.md"
            source.write_text("Ein kurzer vollständiger Testsatz.", encoding="utf-8")

            result = converter.convert_with_cached_calibration(
                source,
                root / "final.mp3",
                calibrator,
                root / "cache",
                keep_chunks=True,
            )

            self.assertIsNotNone(result.chunks_directory)
            assert result.chunks_directory is not None
            self.assertTrue(result.chunks_directory.is_dir())
            self.assertTrue((result.chunks_directory / "raw-001.wav").is_file())
            self.assertTrue((result.chunks_directory / "trimmed-001.wav").is_file())
            self.assertTrue((result.chunks_directory / "combined.wav").is_file())
            self.assertTrue(result.output_path.is_file())

    def test_missing_source_prevents_automatic_calibration_call(self) -> None:
        provider = _SyntheticWavProvider(self.prefill_config.text)
        encoder = _CapturingEncoder()
        rules = ChunkingRules.from_file(PROJECT_ROOT / "config" / "chunking.json")
        converter = PrefillMarkdownAudioConverter(
            self._parser(),
            self._semantic_renderer(),
            SemanticChunker(
                rules,
                reserved_characters=self.prefill_config.reserved_characters,
            ),
            SpeechRenderer(self.profile),
            provider,
            self.provider_config,
            self.profile,
            self.prefill_config,
            WavPrefillTrimmer(self.prefill_config),
            WavAudioJoiner(),
            encoder,
        )
        calibrator = PrefillCalibrator(
            SpeechRenderer(self.profile),
            provider,
            self.prefill_config,
            self.profile,
            self.provider_config,
        )

        with TemporaryDirectory(dir=PROJECT_ROOT) as directory:
            root = Path(directory)

            with self.assertRaises(MarkdownLoadError):
                converter.convert_with_cached_calibration(
                    root / "missing.md",
                    root / "final.mp3",
                    calibrator,
                    root / "cache",
                )

            self.assertEqual(provider.requests, [])
            self.assertFalse((root / "cache").exists())


if __name__ == "__main__":
    unittest.main()
