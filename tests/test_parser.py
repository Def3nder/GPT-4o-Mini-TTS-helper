from pathlib import Path
import unittest

from markdown_tts.ast import (
    BlockQuote,
    CodeBlock,
    Emphasis,
    FootnoteDefinition,
    FootnoteReference,
    Heading,
    InlineCode,
    Link,
    ListBlock,
    Paragraph,
    Strong,
    Table,
    document_text,
    inline_text,
)
from markdown_tts.config import ParserRules
from markdown_tts.loader import load_markdown
from markdown_tts.parser import MarkdownParser


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class MarkdownParserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        rules = ParserRules.from_file(PROJECT_ROOT / "config" / "parser_rules.json")
        cls.parser = MarkdownParser(rules)

    def test_preserves_semantic_markdown_structure(self) -> None:
        document = self.parser.parse(
            "# Kapitel\n\nEin **wichtiger** und *leiser* `Hinweis`.\n\n"
            "- Erster Punkt\n- Zweiter Punkt\n\n> Ein Zitat\n\n```python\nprint('x')\n```\n"
        )

        self.assertIsInstance(document.children[0], Heading)
        paragraph = document.children[1]
        self.assertIsInstance(paragraph, Paragraph)
        assert isinstance(paragraph, Paragraph)
        self.assertTrue(any(isinstance(node, Strong) for node in paragraph.children))
        self.assertTrue(any(isinstance(node, Emphasis) for node in paragraph.children))
        self.assertTrue(any(isinstance(node, InlineCode) for node in paragraph.children))
        self.assertIsInstance(document.children[2], ListBlock)
        self.assertIsInstance(document.children[3], BlockQuote)
        self.assertIsInstance(document.children[4], CodeBlock)

    def test_filters_configured_non_speech_content_after_parsing(self) -> None:
        document = self.parser.parse(
            "---\ntitle: Test\n---\n"
            "Datum: 2026-08-31\n\n"
            "Quelle: Interne Notiz\n\n"
            "<!-- unsichtbar -->\n"
            "Ein Text mit https://example.com/pfad und [lesbarem Link](https://openai.com).\n\n"
            "[ref]: https://example.org\n"
        )

        self.assertEqual(document.front_matter, "title: Test")
        self.assertEqual(len(document.children), 1)
        visible = document_text(document)
        self.assertNotIn("Datum:", visible)
        self.assertNotIn("Quelle:", visible)
        self.assertNotIn("https://", visible)
        self.assertIn("lesbarem Link", visible)

        paragraph = document.children[0]
        assert isinstance(paragraph, Paragraph)
        self.assertTrue(any(isinstance(node, Link) for node in paragraph.children))

    def test_filters_german_date_format(self) -> None:
        document = self.parser.parse("Datum: 02.09.2026\n\nSprechbarer Text\n")

        visible = document_text(document)
        self.assertNotIn("Datum:", visible)
        self.assertIn("Sprechbarer Text", visible)

    def test_keeps_unclosed_front_matter_as_document_content(self) -> None:
        document = self.parser.parse("---\ntitle: Bleibt erhalten\n")

        self.assertIsNone(document.front_matter)
        self.assertIn("title: Bleibt erhalten", document_text(document))

    def test_removes_only_metadata_line_from_multiline_paragraph(self) -> None:
        document = self.parser.parse(
            "Erster Inhalt  \nQuelle: Wird entfernt  \nLetzter Inhalt\n"
        )

        visible = document_text(document)
        self.assertEqual(visible, "Erster Inhalt\nLetzter Inhalt")

    def test_tc_007_v1_parser_reference(self) -> None:
        corpus_path = PROJECT_ROOT / "tests" / "corpus" / "tc_007_v1.md"
        document = self.parser.parse(load_markdown(corpus_path))
        visible = document_text(document)

        self.assertEqual(document.front_matter, "title: Markdown-Stresstest\nprofile: coaching")
        self.assertNotIn("Datum:", visible)
        self.assertNotIn("Quelle:", visible)
        self.assertNotIn("https://", visible)
        self.assertNotIn("Dieser Kommentar", visible)
        self.assertTrue(any(isinstance(node, Heading) for node in document.children))
        self.assertTrue(any(isinstance(node, ListBlock) for node in document.children))
        self.assertTrue(any(isinstance(node, BlockQuote) for node in document.children))
        self.assertTrue(any(isinstance(node, CodeBlock) for node in document.children))
        self.assertTrue(any(isinstance(node, Table) for node in document.children))
        self.assertTrue(any(isinstance(node, FootnoteDefinition) for node in document.children))

        reference_paragraph = next(
            node
            for node in document.children
            if isinstance(node, Paragraph) and "Eine Referenz" in inline_text(node.children)
        )
        self.assertTrue(
            any(isinstance(node, FootnoteReference) for node in reference_paragraph.children)
        )


if __name__ == "__main__":
    unittest.main()
