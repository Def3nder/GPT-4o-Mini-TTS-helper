from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from markdown_tts.application import (
    ChunkedMarkdownMergedAudioConverter,
    ChunkedMarkdownAudioConverter,
    ChunkOutputExistsError,
    MarkdownAudioConverter,
    SpeechInputLimitError,
)
from markdown_tts.audio import AudioOutputExistsError
from markdown_tts.chunker import SemanticChunker
from markdown_tts.config import (
    ChunkingRules,
    ParserRules,
    SemanticRendererRules,
    SpeechProfile,
)
from markdown_tts.parser import MarkdownParser
from markdown_tts.semantic_renderer import SemanticRenderer
from markdown_tts.speech_renderer import SpeechRenderer
from markdown_tts.tts.base import SpeechRequest, SpeechSynthesisResult, SpeechUsage


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class _CapturingProvider:
    def __init__(self) -> None:
        self.request: SpeechRequest | None = None
        self.requests: list[SpeechRequest] = []

    def synthesize(
        self,
        request: SpeechRequest,
        output_path: str | Path,
        *,
        overwrite: bool = False,
    ) -> SpeechSynthesisResult:
        self.request = request
        self.requests.append(request)
        output = Path(output_path)
        output.write_bytes(b"ID3-converted")
        return SpeechSynthesisResult(output, SpeechUsage(10, 20, 30))


class _FailingProvider(_CapturingProvider):
    def synthesize(
        self,
        request: SpeechRequest,
        output_path: str | Path,
        *,
        overwrite: bool = False,
    ) -> SpeechSynthesisResult:
        if self.requests:
            raise RuntimeError("Simulierter Providerfehler")
        return super().synthesize(request, output_path, overwrite=overwrite)


class _ByteJoiningAudioJoiner:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail

    def join(
        self,
        input_paths,
        output_path,
        *,
        overwrite: bool = False,
    ) -> Path:
        if self.fail:
            raise RuntimeError("Simulierter Mergefehler")
        destination = Path(output_path)
        destination.write_bytes(b"".join(Path(path).read_bytes() for path in input_paths))
        return destination


class MarkdownAudioConverterTests(unittest.TestCase):
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

    @staticmethod
    def _speech_renderer() -> SpeechRenderer:
        return SpeechRenderer(
            SpeechProfile.from_file(PROJECT_ROOT / "speech_profiles" / "coaching.json")
        )

    def test_converts_tc_007_through_all_non_network_stages(self) -> None:
        provider = _CapturingProvider()
        converter = MarkdownAudioConverter(
            self._parser(),
            self._semantic_renderer(),
            self._speech_renderer(),
            provider,
        )

        with TemporaryDirectory(dir=PROJECT_ROOT) as directory:
            output = Path(directory) / "tc_007.mp3"
            result = converter.convert(
                PROJECT_ROOT / "tests" / "corpus" / "tc_007_v1.md",
                output,
            )

            self.assertEqual(result.read_bytes(), b"ID3-converted")
            assert provider.request is not None
            self.assertIn("Erstens, Erster nummerierter Punkt", provider.request.text)
            self.assertNotIn("Fußnotentext", provider.request.text)

    def test_reports_completed_synthesis_progress_with_provider_usage(self) -> None:
        provider = _CapturingProvider()
        progress_events = []
        converter = MarkdownAudioConverter(
            self._parser(),
            self._semantic_renderer(),
            self._speech_renderer(),
            provider,
            progress_callback=progress_events.append,
        )

        with TemporaryDirectory(dir=PROJECT_ROOT) as directory:
            output = Path(directory) / "speech.mp3"
            converter.convert(PROJECT_ROOT / "tests" / "corpus" / "tc_007_v1.md", output)

        self.assertEqual(len(progress_events), 1)
        event = progress_events[0]
        self.assertEqual(event.stage, "Dokument")
        self.assertEqual((event.current, event.total), (1, 1))
        self.assertIsNotNone(event.result.usage)
        assert event.result.usage is not None
        self.assertEqual(event.result.usage.total_tokens, 30)

    def test_rejects_oversized_single_request_before_provider_call(self) -> None:
        provider = _CapturingProvider()
        converter = MarkdownAudioConverter(
            self._parser(),
            self._semantic_renderer(),
            self._speech_renderer(),
            provider,
            maximum_request_characters=20,
        )

        with TemporaryDirectory(dir=PROJECT_ROOT) as directory:
            root = Path(directory)
            source = root / "long.md"
            source.write_text("Dieser Sprechtext ist eindeutig zu lang.", encoding="utf-8")
            output = root / "long.mp3"

            with self.assertRaisesRegex(
                SpeechInputLimitError,
                "synthesize-chunks.*synthesize-prefill",
            ):
                converter.convert(source, output)

            self.assertEqual(provider.requests, [])
            self.assertFalse(output.exists())

    def test_generates_numbered_audio_chunks_as_complete_batch(self) -> None:
        provider = _CapturingProvider()
        profile = SpeechProfile.from_file(
            PROJECT_ROOT / "speech_profiles" / "coaching.json"
        )
        rules = replace(
            ChunkingRules.from_file(PROJECT_ROOT / "config" / "chunking.json"),
            max_characters=120,
            preferred_minimum_characters=40,
        )
        converter = ChunkedMarkdownAudioConverter(
            self._parser(),
            self._semantic_renderer(),
            SemanticChunker(rules),
            SpeechRenderer(profile),
            provider,
            "mp3",
        )

        with TemporaryDirectory(dir=PROJECT_ROOT) as directory:
            temporary_root = Path(directory)
            source = temporary_root / "artikel.md"
            source.write_text(
                "# Kapitel\n\n"
                + " ".join(
                    f"Dies ist der vollständige Testsatz Nummer {number}."
                    for number in range(1, 13)
                ),
                encoding="utf-8",
            )
            output_directory = temporary_root / "chunks"

            outputs = converter.convert(source, output_directory)

            self.assertGreater(len(outputs), 1)
            self.assertEqual(
                [path.name for path in outputs],
                [
                    f"artikel.part-{index:03d}.mp3"
                    for index in range(1, len(outputs) + 1)
                ],
            )
            self.assertTrue(all(path.read_bytes() == b"ID3-converted" for path in outputs))
            self.assertTrue(all(len(request.text) <= 120 for request in provider.requests))
            self.assertTrue(
                all(
                    request.instructions == profile.instructions
                    for request in provider.requests
                )
            )

    def test_checks_all_chunk_destinations_before_provider_calls(self) -> None:
        provider = _CapturingProvider()
        converter = ChunkedMarkdownAudioConverter(
            self._parser(),
            self._semantic_renderer(),
            SemanticChunker(
                ChunkingRules.from_file(PROJECT_ROOT / "config" / "chunking.json")
            ),
            self._speech_renderer(),
            provider,
            "mp3",
        )

        with TemporaryDirectory(dir=PROJECT_ROOT) as directory:
            temporary_root = Path(directory)
            source = temporary_root / "artikel.md"
            source.write_text("Ein kurzer Test.", encoding="utf-8")
            output_directory = temporary_root / "chunks"
            output_directory.mkdir()
            existing = output_directory / "artikel.part-001.mp3"
            existing.write_bytes(b"existing")

            with self.assertRaises(ChunkOutputExistsError):
                converter.convert(source, output_directory)

            self.assertEqual(provider.requests, [])
            self.assertEqual(existing.read_bytes(), b"existing")

    def test_does_not_publish_partial_batch_after_provider_failure(self) -> None:
        provider = _FailingProvider()
        rules = replace(
            ChunkingRules.from_file(PROJECT_ROOT / "config" / "chunking.json"),
            max_characters=80,
            preferred_minimum_characters=30,
        )
        converter = ChunkedMarkdownAudioConverter(
            self._parser(),
            self._semantic_renderer(),
            SemanticChunker(rules),
            self._speech_renderer(),
            provider,
            "mp3",
        )

        with TemporaryDirectory(dir=PROJECT_ROOT) as directory:
            temporary_root = Path(directory)
            source = temporary_root / "artikel.md"
            source.write_text(
                "Erster vollständiger Satz mit genügend Text. "
                "Zweiter vollständiger Satz mit genügend Text. "
                "Dritter vollständiger Satz mit genügend Text.",
                encoding="utf-8",
            )
            output_directory = temporary_root / "chunks"

            with self.assertRaisesRegex(RuntimeError, "Providerfehler"):
                converter.convert(source, output_directory)

            self.assertEqual(list(output_directory.glob("*.mp3")), [])
            retained = list(output_directory.glob(".artikel-chunks-*"))
            self.assertEqual(len(retained), 1)
            retained_chunks = list(retained[0].glob("*.mp3"))
            self.assertEqual(len(retained_chunks), 1)
            self.assertEqual(retained_chunks[0].read_bytes(), b"ID3-converted")

    def test_merges_chunks_and_removes_temporary_directory_after_success(self) -> None:
        provider = _CapturingProvider()
        chunk_converter = ChunkedMarkdownAudioConverter(
            self._parser(),
            self._semantic_renderer(),
            SemanticChunker(
                ChunkingRules.from_file(PROJECT_ROOT / "config" / "chunking.json")
            ),
            self._speech_renderer(),
            provider,
            "mp3",
        )
        converter = ChunkedMarkdownMergedAudioConverter(
            chunk_converter,
            _ByteJoiningAudioJoiner(),
        )

        with TemporaryDirectory(dir=PROJECT_ROOT) as directory:
            root = Path(directory)
            source = root / "artikel.md"
            source.write_text("Ein kurzer vollständiger Testsatz.", encoding="utf-8")
            output = root / "artikel_coaching.mp3"

            result = converter.convert(source, output)

            self.assertEqual(result.output_path, output)
            self.assertIsNone(result.chunks_directory)
            self.assertEqual(output.read_bytes(), b"ID3-converted")
            self.assertFalse((root / "artikel_coaching").exists())

    def test_keeps_named_chunk_directory_on_request_or_merge_failure(self) -> None:
        for fail, keep_chunks in ((False, True), (True, False)):
            with self.subTest(fail=fail, keep_chunks=keep_chunks):
                provider = _CapturingProvider()
                chunk_converter = ChunkedMarkdownAudioConverter(
                    self._parser(),
                    self._semantic_renderer(),
                    SemanticChunker(
                        ChunkingRules.from_file(
                            PROJECT_ROOT / "config" / "chunking.json"
                        )
                    ),
                    self._speech_renderer(),
                    provider,
                    "mp3",
                )
                converter = ChunkedMarkdownMergedAudioConverter(
                    chunk_converter,
                    _ByteJoiningAudioJoiner(fail=fail),
                )
                with TemporaryDirectory(dir=PROJECT_ROOT) as directory:
                    root = Path(directory)
                    source = root / "artikel.md"
                    source.write_text("Ein kurzer vollständiger Testsatz.", encoding="utf-8")
                    output = root / "hörbuch.mp3"

                    if fail:
                        with self.assertRaisesRegex(RuntimeError, "Mergefehler"):
                            converter.convert(source, output)
                    else:
                        result = converter.convert(
                            source,
                            output,
                            keep_chunks=keep_chunks,
                        )
                        self.assertEqual(result.chunks_directory, root / "hörbuch")

                    chunks_directory = root / "hörbuch"
                    self.assertTrue(chunks_directory.is_dir())
                    self.assertTrue(list(chunks_directory.glob("*.mp3")))

    def test_existing_merged_output_prevents_paid_chunk_calls(self) -> None:
        provider = _CapturingProvider()
        converter = ChunkedMarkdownMergedAudioConverter(
            ChunkedMarkdownAudioConverter(
                self._parser(),
                self._semantic_renderer(),
                SemanticChunker(
                    ChunkingRules.from_file(PROJECT_ROOT / "config" / "chunking.json")
                ),
                self._speech_renderer(),
                provider,
                "mp3",
            ),
            _ByteJoiningAudioJoiner(),
        )

        with TemporaryDirectory(dir=PROJECT_ROOT) as directory:
            root = Path(directory)
            source = root / "artikel.md"
            source.write_text("Ein kurzer vollständiger Testsatz.", encoding="utf-8")
            output = root / "artikel.mp3"
            output.write_bytes(b"existing")

            with self.assertRaises(AudioOutputExistsError):
                converter.convert(source, output)

            self.assertEqual(provider.requests, [])
            self.assertEqual(output.read_bytes(), b"existing")


if __name__ == "__main__":
    unittest.main()
