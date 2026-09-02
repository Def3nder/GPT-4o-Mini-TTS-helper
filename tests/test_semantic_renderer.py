from pathlib import Path
import unittest

from markdown_tts.config import ParserRules, SemanticRendererRules
from markdown_tts.loader import load_markdown
from markdown_tts.parser import MarkdownParser
from markdown_tts.semantic_renderer import SemanticRenderer


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class SemanticRendererTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        parser_rules = ParserRules.from_file(PROJECT_ROOT / "config" / "parser_rules.json")
        renderer_rules = SemanticRendererRules.from_file(
            PROJECT_ROOT / "config" / "semantic_renderer.json"
        )
        cls.parser = MarkdownParser(parser_rules)
        cls.renderer = SemanticRenderer(renderer_rules)

    def test_tc_007_v1_produces_speakable_text(self) -> None:
        source = load_markdown(PROJECT_ROOT / "tests" / "corpus" / "tc_007_v1.md")
        speech = self.renderer.render(self.parser.parse(source))

        self.assertIn("Erstens, Erster nummerierter Punkt", speech.text)
        self.assertIn("Zweitens, Zweiter nummerierter Punkt", speech.text)
        self.assertIn("Verschachtelter Aufzählungspunkt", speech.text)
        self.assertIn("Eine Referenz beendet den Test.", speech.text)
        self.assertNotIn("Begriff", speech.text)
        self.assertNotIn("Dokumentstruktur", speech.text)
        self.assertNotIn("print(", speech.text)
        self.assertNotIn("Beschreibendes Bild", speech.text)
        self.assertNotIn("[^1]", speech.text)
        self.assertNotIn("Fußnotentext", speech.text)
        self.assertNotIn("https://", speech.text)

    def test_preserves_emphasis_as_positioned_speech_cues(self) -> None:
        document = self.parser.parse("# **Wichtig**\n\nDas ist *leise* und **entscheidend**.")
        speech = self.renderer.render(document)

        cues = [
            (block.emphasized_text(cue), cue.kind)
            for block in speech.blocks
            for cue in block.emphasis_cues
        ]
        self.assertIn(("Wichtig", "strong"), cues)
        self.assertIn(("leise", "emphasis"), cues)
        self.assertIn(("entscheidend", "strong"), cues)

    def test_uses_configured_fallback_for_large_ordered_numbers(self) -> None:
        speech = self.renderer.render(self.parser.parse("12. Zwölfter Eintrag"))

        self.assertEqual(speech.text, "Punkt 12, Zwölfter Eintrag")

    def test_removes_blocks_containing_only_punctuation(self) -> None:
        document = self.parser.parse(".\n\n...\n\n—\n\nEin normaler Satz bleibt!")

        speech = self.renderer.render(document)

        self.assertEqual(speech.text, "Ein normaler Satz bleibt!")

    def test_keeps_punctuation_inside_speakable_text(self) -> None:
        document = self.parser.parse("Warte ... ist das wirklich richtig?")

        speech = self.renderer.render(document)

        self.assertEqual(speech.text, "Warte ... ist das wirklich richtig?")


if __name__ == "__main__":
    unittest.main()
