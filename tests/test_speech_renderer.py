from pathlib import Path
import unittest

from markdown_tts.config import ParserRules, SemanticRendererRules, SpeechProfile
from markdown_tts.loader import load_markdown
from markdown_tts.parser import MarkdownParser
from markdown_tts.semantic_renderer import SemanticRenderer, SpeechDocument
from markdown_tts.speech_renderer import EmptySpeechDocumentError, SpeechRenderer


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class SpeechRendererTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.profile = SpeechProfile.from_file(
            PROJECT_ROOT / "speech_profiles" / "coaching.json"
        )

    def test_builds_provider_request_with_global_profile_only(self) -> None:
        parser = MarkdownParser(
            ParserRules.from_file(PROJECT_ROOT / "config" / "parser_rules.json")
        )
        semantic_renderer = SemanticRenderer(
            SemanticRendererRules.from_file(
                PROJECT_ROOT / "config" / "semantic_renderer.json"
            )
        )
        ast_document = parser.parse(
            load_markdown(PROJECT_ROOT / "tests" / "corpus" / "tc_007_v1.md")
        )
        speech_document = semantic_renderer.render(ast_document)

        request = SpeechRenderer(self.profile).render(speech_document)

        self.assertEqual(request.text, speech_document.text)
        self.assertEqual(request.voice, "cedar")
        self.assertEqual(request.speed, 0.95)
        self.assertEqual(request.instructions, self.profile.instructions)
        self.assertNotIn('"Betonung"', request.instructions)
        self.assertNotIn('"fetten Text"', request.instructions)
        self.assertNotIn('"kursiven Text"', request.instructions)

    def test_rejects_empty_speech_document(self) -> None:
        empty = SpeechDocument(blocks=(), block_separator="\n\n")

        with self.assertRaisesRegex(EmptySpeechDocumentError, "keinen sprechbaren Text"):
            SpeechRenderer(self.profile).render(empty)


if __name__ == "__main__":
    unittest.main()
