from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from markdown_tts.loader import MarkdownLoadError, load_markdown


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class MarkdownLoaderTests(unittest.TestCase):
    def test_loads_utf8_with_bom(self) -> None:
        with TemporaryDirectory(dir=PROJECT_ROOT) as directory:
            path = Path(directory) / "input.md"
            path.write_bytes(b"\xef\xbb\xbf# Gr\xc3\xbc\xc3\x9fe")

            self.assertEqual(load_markdown(path), "# Grüße")

    def test_rejects_non_utf8_input_with_actionable_message(self) -> None:
        with TemporaryDirectory(dir=PROJECT_ROOT) as directory:
            path = Path(directory) / "input.md"
            path.write_bytes(b"Text: \x80")

            with self.assertRaisesRegex(MarkdownLoadError, "als UTF-8 speichern"):
                load_markdown(path)


if __name__ == "__main__":
    unittest.main()
