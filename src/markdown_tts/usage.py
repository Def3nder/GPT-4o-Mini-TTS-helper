"""Provider-reported speech usage aggregation and configured cost calculation."""

from __future__ import annotations

from dataclasses import dataclass

from markdown_tts.config import TTSProviderConfig
from markdown_tts.tts.base import SpeechUsage


@dataclass(frozen=True, slots=True)
class SpeechCost:
    """Calculated cost from actual usage and configured model prices."""

    currency: str
    input_cost: float
    output_cost: float
    total_cost: float


@dataclass(slots=True)
class SpeechUsageAccumulator:
    """Accumulate actual provider usage across one application run."""

    request_count: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0

    def add(self, usage: SpeechUsage) -> None:
        self.request_count += 1
        self.input_tokens += usage.input_tokens
        self.output_tokens += usage.output_tokens
        self.total_tokens += usage.total_tokens

    @property
    def usage(self) -> SpeechUsage:
        return SpeechUsage(
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
            total_tokens=self.total_tokens,
        )


def calculate_speech_cost(
    usage: SpeechUsage,
    config: TTSProviderConfig,
) -> SpeechCost:
    """Calculate, but never claim, billing cost from actual token usage."""
    input_cost = (
        usage.input_tokens * config.input_token_price_per_million / 1_000_000
    )
    output_cost = (
        usage.output_tokens * config.output_token_price_per_million / 1_000_000
    )
    return SpeechCost(
        currency=config.pricing_currency,
        input_cost=input_cost,
        output_cost=output_cost,
        total_cost=input_cost + output_cost,
    )
