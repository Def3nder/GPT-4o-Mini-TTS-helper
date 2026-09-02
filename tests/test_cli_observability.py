from contextlib import redirect_stdout
from io import StringIO
import logging
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from markdown_tts.cli import _CliSynthesisReporter, _configure_logging
from markdown_tts.config import TTSProviderConfig
from markdown_tts.progress import SynthesisProgress
from markdown_tts.tts.base import SpeechSynthesisResult, SpeechUsage


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class CliObservabilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = TTSProviderConfig.from_file(
            PROJECT_ROOT / "config" / "tts_provider.json"
        )

    def test_formats_progress_usage_and_calculated_cost_summary(self) -> None:
        reporter = _CliSynthesisReporter(self.config, enabled=True)
        progress = SynthesisProgress(
            stage="Chunk",
            current=1,
            total=2,
            text_characters=3_627,
            result=SpeechSynthesisResult(
                Path("chunk.mp3"),
                SpeechUsage(1_000, 2_000, 3_000),
            ),
        )
        output = StringIO()

        with redirect_stdout(output):
            reporter(progress)
            reporter.print_summary()

        rendered = output.getvalue()
        self.assertIn("[Chunk 1/2] 3.627 Zeichen", rendered)
        self.assertIn("1.000 Input + 2.000 Audio-Output = 3.000 Tokens", rendered)
        self.assertIn("Berechnete Kosten:", rendered)
        self.assertIn("0,024600 USD", rendered)
        self.assertIn("Geldbetrag lokal berechnet", rendered)

    def test_writes_configured_utf8_log_file(self) -> None:
        with TemporaryDirectory(dir=PROJECT_ROOT) as directory:
            log_path = Path(directory) / "run.log"
            _configure_logging("INFO", log_path)

            logging.getLogger("markdown_tts.test").info("Fortschritt äöü")
            for handler in logging.getLogger().handlers:
                handler.flush()

            self.assertIn("Fortschritt äöü", log_path.read_text(encoding="utf-8"))
            logging.basicConfig(
                level=logging.WARNING,
                handlers=[logging.NullHandler()],
                force=True,
            )


if __name__ == "__main__":
    unittest.main()
