from dataclasses import replace
from pathlib import Path
import unittest

from markdown_tts.chunker import SemanticChunker, UnchunkableSpeechError
from markdown_tts.config import ChunkingRules
from markdown_tts.semantic_renderer import EmphasisCue, SpeechBlock, SpeechDocument


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class SemanticChunkerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.default_rules = ChunkingRules.from_file(
            PROJECT_ROOT / "config" / "chunking.json"
        )

    def test_starts_heading_in_new_chunk_and_keeps_following_paragraph(self) -> None:
        rules = replace(
            self.default_rules,
            max_characters=50,
            preferred_minimum_characters=15,
        )
        document = SpeechDocument(
            blocks=(
                SpeechBlock("paragraph", "Ein einleitender Absatz mit Inhalt."),
                SpeechBlock("heading_1", "Neues Kapitel."),
                SpeechBlock("paragraph", "Der zugehörige kurze Absatz."),
            ),
            block_separator="\n\n",
        )

        chunks = SemanticChunker(rules).chunk(document)

        self.assertEqual(len(chunks), 2)
        self.assertEqual(chunks[0].blocks[0].kind, "paragraph")
        self.assertEqual(chunks[1].blocks[0].kind, "heading_1")
        self.assertIn("Der zugehörige kurze Absatz.", chunks[1].text)

    def test_splits_oversized_paragraph_at_sentence_boundaries(self) -> None:
        rules = replace(
            self.default_rules,
            max_characters=55,
            preferred_minimum_characters=20,
        )
        text = (
            "Der erste vollständige Satz endet hier. "
            "Der zweite vollständige Satz endet hier. "
            "Der dritte Satz endet."
        )
        document = SpeechDocument(
            blocks=(SpeechBlock("paragraph", text),),
            block_separator="\n\n",
        )

        chunks = SemanticChunker(rules).chunk(document)

        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(chunk.character_count <= 55 for chunk in chunks))
        self.assertTrue(all(chunk.text.endswith(".") for chunk in chunks))
        self.assertEqual(
            " ".join(chunk.text for chunk in chunks).split(),
            text.split(),
        )

    def test_preserves_emphasis_cue_positions_after_split(self) -> None:
        rules = replace(
            self.default_rules,
            max_characters=40,
            preferred_minimum_characters=15,
        )
        text = "Ein kurzer Anfang. Wichtiger Hinweis. Ende."
        cue_start = text.index("Wichtiger Hinweis")
        document = SpeechDocument(
            blocks=(
                SpeechBlock(
                    "paragraph",
                    text,
                    (EmphasisCue(cue_start, cue_start + len("Wichtiger Hinweis"), "strong"),),
                ),
            ),
            block_separator="\n\n",
        )

        chunks = SemanticChunker(rules).chunk(document)

        emphasized = [
            block.emphasized_text(cue)
            for chunk in chunks
            for block in chunk.blocks
            for cue in block.emphasis_cues
        ]
        self.assertEqual(emphasized, ["Wichtiger Hinweis"])

    def test_uses_word_boundary_only_as_last_fallback(self) -> None:
        rules = replace(
            self.default_rules,
            max_characters=24,
            preferred_minimum_characters=10,
        )
        text = "Dieser absichtlich lange Satz besitzt keine Satzzeichen bis zum Schluss"
        document = SpeechDocument(
            blocks=(SpeechBlock("paragraph", text),),
            block_separator="\n\n",
        )

        chunks = SemanticChunker(rules).chunk(document)

        self.assertTrue(all(chunk.character_count <= 24 for chunk in chunks))
        self.assertEqual(
            " ".join(chunk.text for chunk in chunks).split(),
            text.split(),
        )

    def test_rejects_word_that_exceeds_limit(self) -> None:
        rules = replace(
            self.default_rules,
            max_characters=10,
            preferred_minimum_characters=5,
            allow_whitespace_fallback=False,
        )
        document = SpeechDocument(
            blocks=(SpeechBlock("paragraph", "abcdefghijklmnop"),),
            block_separator="\n\n",
        )

        with self.assertRaisesRegex(UnchunkableSpeechError, "Wortgrenze"):
            SemanticChunker(rules).chunk(document)

    def test_reserves_request_capacity_for_prefill_text(self) -> None:
        rules = replace(
            self.default_rules,
            max_characters=60,
            preferred_minimum_characters=20,
        )
        document = SpeechDocument(
            blocks=(
                SpeechBlock(
                    "paragraph",
                    "Erster vollständiger Satz. Zweiter vollständiger Satz.",
                ),
            ),
            block_separator="\n\n",
        )

        chunks = SemanticChunker(rules, reserved_characters=15).chunk(document)

        self.assertTrue(all(chunk.character_count <= 45 for chunk in chunks))
        self.assertTrue(all(chunk.character_count + 15 <= 60 for chunk in chunks))

    def test_rejects_prefill_reservation_without_body_capacity(self) -> None:
        with self.assertRaisesRegex(UnchunkableSpeechError, "keinen Platz"):
            SemanticChunker(self.default_rules, reserved_characters=3800)


if __name__ == "__main__":
    unittest.main()
