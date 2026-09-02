from pathlib import Path
import unittest

from markdown_tts.config import TTSProviderConfig
from markdown_tts.tts.base import SpeechUsage
from markdown_tts.usage import SpeechUsageAccumulator, calculate_speech_cost


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class SpeechUsageTests(unittest.TestCase):
    def test_aggregates_reported_usage_and_calculates_configured_cost(self) -> None:
        config = TTSProviderConfig.from_file(
            PROJECT_ROOT / "config" / "tts_provider.json"
        )
        accumulator = SpeechUsageAccumulator()
        accumulator.add(SpeechUsage(1_000, 2_000, 3_000))
        accumulator.add(SpeechUsage(500, 1_000, 1_500))

        cost = calculate_speech_cost(accumulator.usage, config)

        self.assertEqual(accumulator.request_count, 2)
        self.assertEqual(accumulator.input_tokens, 1_500)
        self.assertEqual(accumulator.output_tokens, 3_000)
        self.assertEqual(accumulator.total_tokens, 4_500)
        self.assertAlmostEqual(cost.input_cost, 0.0009)
        self.assertAlmostEqual(cost.output_cost, 0.036)
        self.assertAlmostEqual(cost.total_cost, 0.0369)
        self.assertEqual(cost.currency, "USD")


if __name__ == "__main__":
    unittest.main()
