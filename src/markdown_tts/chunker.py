"""Split semantic speech documents at natural language boundaries."""

from __future__ import annotations

from dataclasses import dataclass
import logging

from markdown_tts.config import ChunkingRules
from markdown_tts.semantic_renderer import EmphasisCue, SpeechBlock, SpeechDocument


LOGGER = logging.getLogger(__name__)


class UnchunkableSpeechError(ValueError):
    """Raised when text cannot be split without cutting through a word."""


@dataclass(frozen=True, slots=True)
class SpeechChunk:
    """One provider-independent portion of a semantic speech document."""

    index: int
    blocks: tuple[SpeechBlock, ...]
    block_separator: str

    @property
    def text(self) -> str:
        """Return the plain text contained in this chunk."""
        return self.block_separator.join(block.text for block in self.blocks)

    @property
    def character_count(self) -> int:
        """Return the exact number of characters sent as speech input."""
        return len(self.text)

    def as_document(self) -> SpeechDocument:
        """Expose the chunk through the existing SpeechRenderer contract."""
        return SpeechDocument(
            blocks=self.blocks,
            block_separator=self.block_separator,
        )


class SemanticChunker:
    """Split speech blocks while preferring structural and sentence boundaries."""

    def __init__(self, rules: ChunkingRules, *, reserved_characters: int = 0) -> None:
        if isinstance(reserved_characters, bool) or reserved_characters < 0:
            raise UnchunkableSpeechError(
                "Die reservierte Zeichenzahl darf nicht negativ sein."
            )
        effective_limit = rules.max_characters - reserved_characters
        if effective_limit <= 0:
            raise UnchunkableSpeechError(
                "Die reservierte Zeichenzahl lässt keinen Platz für den eigentlichen Sprechtext."
            )
        self._rules = rules
        self._reserved_characters = reserved_characters
        self._effective_limit = effective_limit

    @property
    def maximum_request_characters(self) -> int:
        """Return the configured total request limit including reserved overhead."""
        return self._rules.max_characters

    @property
    def effective_text_characters(self) -> int:
        """Return the limit available to semantic chunk text."""
        return self._effective_limit

    def chunk(self, document: SpeechDocument) -> tuple[SpeechChunk, ...]:
        """Create ordered chunks whose text stays within the configured limit."""
        chunks: list[SpeechChunk] = []
        current: list[SpeechBlock] = []

        def current_length() -> int:
            if not current:
                return 0
            separator_length = len(document.block_separator) * (len(current) - 1)
            return sum(len(block.text) for block in current) + separator_length

        def flush() -> None:
            if not current:
                return
            chunks.append(
                SpeechChunk(
                    index=len(chunks) + 1,
                    blocks=tuple(current),
                    block_separator=document.block_separator,
                )
            )
            current.clear()

        for source_block in document.blocks:
            if (
                self._rules.start_new_chunk_at_headings
                and self._is_heading(source_block)
                and current
            ):
                flush()

            pending = source_block
            while pending is not None:
                separator_length = len(document.block_separator) if current else 0
                available = (
                    self._effective_limit
                    - current_length()
                    - separator_length
                )

                if len(pending.text) <= available:
                    current.append(pending)
                    pending = None
                    continue

                pending_fits_empty_chunk = len(pending.text) <= self._effective_limit
                heading_needs_content = len(current) == 1 and self._is_heading(current[0])
                enough_space_for_split = (
                    available >= self._rules.preferred_minimum_characters
                )

                if current and pending_fits_empty_chunk and not heading_needs_content:
                    flush()
                    continue

                if current and not (heading_needs_content or enough_space_for_split):
                    flush()
                    continue

                try:
                    first, remainder = self._split_once(pending, available)
                except UnchunkableSpeechError:
                    if current:
                        flush()
                        continue
                    raise

                current.append(first)
                pending = remainder
                if pending is not None:
                    flush()

        flush()
        LOGGER.info(
            "Sprechdokument in %d Chunk(s) mit maximal %d Zeichen aufgeteilt.",
            len(chunks),
            self._effective_limit,
        )
        return tuple(chunks)

    def _split_once(
        self,
        block: SpeechBlock,
        limit: int,
    ) -> tuple[SpeechBlock, SpeechBlock | None]:
        if len(block.text) <= limit:
            return block, None
        if limit <= 0:
            raise UnchunkableSpeechError(
                "Für den nächsten Textblock ist im aktuellen Chunk kein Platz verfügbar."
            )

        split_index = self._find_split_index(block.text, limit)
        if split_index is None:
            preview = block.text[:80].replace("\n", " ")
            raise UnchunkableSpeechError(
                f"Ein Textabschnitt kann innerhalb des Limits von {limit} Zeichen nicht "
                f"an einer Wortgrenze getrennt werden: '{preview}…'"
            )

        first = self._slice_block(block, 0, split_index)
        remainder = self._slice_block(block, split_index, len(block.text))
        return first, remainder

    def _find_split_index(self, text: str, limit: int) -> int | None:
        minimum_index = max(1, int(limit * self._rules.minimum_split_ratio))
        boundary_groups = (
            self._rules.structural_break_characters,
            self._rules.sentence_end_characters,
            self._rules.clause_end_characters,
            self._rules.comma_characters,
        )
        for characters in boundary_groups:
            boundary = self._last_boundary(text, characters, minimum_index, limit)
            if boundary is not None:
                return boundary

        if self._rules.allow_whitespace_fallback:
            upper_index = min(limit, len(text) - 1)
            for index in range(upper_index, 0, -1):
                if text[index].isspace():
                    return index
        return None

    @staticmethod
    def _last_boundary(
        text: str,
        characters: str,
        minimum_index: int,
        limit: int,
    ) -> int | None:
        upper_index = min(limit - 1, len(text) - 1)
        for index in range(upper_index, minimum_index - 1, -1):
            if text[index] not in characters:
                continue
            following_index = index + 1
            if following_index == len(text) or text[following_index].isspace():
                return following_index
        return None

    @staticmethod
    def _slice_block(block: SpeechBlock, start: int, end: int) -> SpeechBlock:
        raw_text = block.text[start:end]
        leading_whitespace = len(raw_text) - len(raw_text.lstrip())
        trailing_whitespace = len(raw_text) - len(raw_text.rstrip())
        content_start = start + leading_whitespace
        content_end = end - trailing_whitespace
        text = block.text[content_start:content_end]

        cues = tuple(
            EmphasisCue(
                start=max(cue.start, content_start) - content_start,
                end=min(cue.end, content_end) - content_start,
                kind=cue.kind,
            )
            for cue in block.emphasis_cues
            if cue.start < content_end and cue.end > content_start
        )
        return SpeechBlock(kind=block.kind, text=text, emphasis_cues=cues)

    @staticmethod
    def _is_heading(block: SpeechBlock) -> bool:
        return block.kind.startswith("heading_")
