"""Render a document AST into structured, speakable text."""

from __future__ import annotations

from dataclasses import dataclass

from markdown_tts.ast import (
    BlockNode,
    BlockQuote,
    CodeBlock,
    Document,
    Emphasis,
    FootnoteDefinition,
    FootnoteReference,
    Heading,
    HtmlBlock,
    Image,
    InlineCode,
    InlineNode,
    LineBreak,
    Link,
    ListBlock,
    Paragraph,
    Strong,
    Table,
    Text,
    ThematicBreak,
    inline_text,
)
from markdown_tts.config import SemanticRendererRules


@dataclass(frozen=True, slots=True)
class EmphasisCue:
    start: int
    end: int
    kind: str


@dataclass(frozen=True, slots=True)
class SpeechBlock:
    kind: str
    text: str
    emphasis_cues: tuple[EmphasisCue, ...] = ()

    def emphasized_text(self, cue: EmphasisCue) -> str:
        """Return the text span addressed by one emphasis cue."""
        return self.text[cue.start : cue.end]


@dataclass(frozen=True, slots=True)
class SpeechDocument:
    blocks: tuple[SpeechBlock, ...]
    block_separator: str

    @property
    def text(self) -> str:
        """Return the final plain text intended for speech generation."""
        return self.block_separator.join(block.text for block in self.blocks)


@dataclass(frozen=True, slots=True)
class _RenderedInline:
    text: str
    cues: tuple[EmphasisCue, ...] = ()


class SemanticRenderer:
    """Convert semantic AST nodes into provider-independent speech blocks."""

    def __init__(self, rules: SemanticRendererRules) -> None:
        self._rules = rules

    def render(self, document: Document) -> SpeechDocument:
        """Render speakable blocks while preserving emphasis as structured cues."""
        blocks = tuple(
            speech_block
            for node in document.children
            if (speech_block := self._render_block(node)) is not None
        )
        return SpeechDocument(blocks=blocks, block_separator=self._rules.block_separator)

    def _render_block(self, node: BlockNode) -> SpeechBlock | None:
        if isinstance(node, Paragraph):
            return self._speech_block("paragraph", self._render_inlines(node.children))

        if isinstance(node, Heading):
            rendered = self._trim(self._render_inlines(node.children))
            if not rendered.text:
                return None
            if self._rules.heading_suffix and not rendered.text.endswith(self._rules.heading_suffix):
                rendered = _RenderedInline(
                    text=rendered.text + self._rules.heading_suffix,
                    cues=rendered.cues,
                )
            return SpeechBlock(
                kind=f"heading_{node.level}",
                text=rendered.text,
                emphasis_cues=rendered.cues,
            )

        if isinstance(node, ListBlock):
            return self._render_list(node)

        if isinstance(node, BlockQuote):
            children = tuple(
                block
                for child in node.children
                if (block := self._render_block(child)) is not None
            )
            combined = self._join_blocks(children, self._rules.block_separator)
            return self._speech_block(
                "blockquote",
                self._prefix(self._rules.quote_prefix, combined),
            )

        if isinstance(node, Table):
            if not self._rules.speak_tables:
                return None
            rows = [
                self._rules.table_cell_separator.join(
                    inline_text(cell.children).strip() for cell in row.cells
                )
                for row in node.rows
            ]
            return self._speech_block(
                "table",
                _RenderedInline(self._rules.table_row_separator.join(filter(None, rows))),
            )

        if isinstance(node, CodeBlock):
            if not self._rules.speak_code_blocks:
                return None
            return self._speech_block("code_block", _RenderedInline(node.value))

        if isinstance(node, FootnoteDefinition):
            if not self._rules.speak_footnotes:
                return None
            children = tuple(
                block
                for child in node.children
                if (block := self._render_block(child)) is not None
            )
            combined = self._join_blocks(children, self._rules.block_separator)
            prefix = self._rules.footnote_prefix.format(label=node.label)
            return self._speech_block("footnote", self._prefix(prefix, combined))

        if isinstance(node, (HtmlBlock, ThematicBreak)):
            return None
        return None

    def _render_list(self, node: ListBlock) -> SpeechBlock | None:
        rendered_items: list[_RenderedInline] = []
        first_number = node.start or 1
        for offset, item in enumerate(node.items):
            child_blocks = tuple(
                block
                for child in item.children
                if (block := self._render_block(child)) is not None
            )
            rendered = self._join_blocks(child_blocks, self._rules.list_item_separator)
            if not rendered.text:
                continue

            if node.ordered:
                number = first_number + offset
                marker = self._ordered_marker(number)
            else:
                marker = self._rules.unordered_list_marker
            prefix = marker + self._rules.list_marker_suffix if marker else ""
            rendered_items.append(self._prefix(prefix, rendered))

        if not rendered_items:
            return None
        combined = self._join_inlines(rendered_items, self._rules.list_item_separator)
        kind = "ordered_list" if node.ordered else "unordered_list"
        return self._speech_block(kind, combined)

    def _ordered_marker(self, number: int) -> str:
        marker_index = number - 1
        if 0 <= marker_index < len(self._rules.ordered_list_markers):
            return self._rules.ordered_list_markers[marker_index]
        return self._rules.ordered_list_fallback.format(number=number)

    def _render_inlines(self, nodes: tuple[InlineNode, ...]) -> _RenderedInline:
        rendered_parts: list[_RenderedInline] = []
        for node in nodes:
            if isinstance(node, Text):
                rendered_parts.append(_RenderedInline(node.value))
            elif isinstance(node, InlineCode):
                if self._rules.speak_inline_code:
                    rendered_parts.append(_RenderedInline(node.value))
            elif isinstance(node, LineBreak):
                rendered_parts.append(_RenderedInline("\n" if node.hard else " "))
            elif isinstance(node, Link):
                rendered_parts.append(self._render_inlines(node.children))
            elif isinstance(node, Image):
                if self._rules.speak_image_alt_text:
                    rendered_parts.append(_RenderedInline(node.alt_text))
            elif isinstance(node, FootnoteReference):
                if self._rules.speak_footnotes:
                    rendered_parts.append(
                        _RenderedInline(self._rules.footnote_prefix.format(label=node.label).strip())
                    )
            elif isinstance(node, (Strong, Emphasis)):
                nested = self._render_inlines(node.children)
                if nested.text:
                    kind = "strong" if isinstance(node, Strong) else "emphasis"
                    cue = EmphasisCue(start=0, end=len(nested.text), kind=kind)
                    rendered_parts.append(
                        _RenderedInline(nested.text, nested.cues + (cue,))
                    )
        return self._join_inlines(rendered_parts, "")

    def _speech_block(self, kind: str, rendered: _RenderedInline) -> SpeechBlock | None:
        trimmed = self._trim(rendered)
        if not trimmed.text:
            return None
        if (
            self._rules.remove_punctuation_only_blocks
            and not any(character.isalnum() for character in trimmed.text)
        ):
            return None
        return SpeechBlock(kind=kind, text=trimmed.text, emphasis_cues=trimmed.cues)

    @staticmethod
    def _prefix(prefix: str, rendered: _RenderedInline) -> _RenderedInline:
        if not prefix:
            return rendered
        shift = len(prefix)
        return _RenderedInline(
            text=prefix + rendered.text,
            cues=tuple(
                EmphasisCue(cue.start + shift, cue.end + shift, cue.kind)
                for cue in rendered.cues
            ),
        )

    @staticmethod
    def _join_blocks(blocks: tuple[SpeechBlock, ...], separator: str) -> _RenderedInline:
        return SemanticRenderer._join_inlines(
            [_RenderedInline(block.text, block.emphasis_cues) for block in blocks],
            separator,
        )

    @staticmethod
    def _join_inlines(parts: list[_RenderedInline], separator: str) -> _RenderedInline:
        text_parts: list[str] = []
        cues: list[EmphasisCue] = []
        offset = 0
        for index, part in enumerate(parts):
            if index:
                text_parts.append(separator)
                offset += len(separator)
            text_parts.append(part.text)
            cues.extend(
                EmphasisCue(cue.start + offset, cue.end + offset, cue.kind)
                for cue in part.cues
            )
            offset += len(part.text)
        return _RenderedInline("".join(text_parts), tuple(cues))

    @staticmethod
    def _trim(rendered: _RenderedInline) -> _RenderedInline:
        leading = len(rendered.text) - len(rendered.text.lstrip())
        text = rendered.text.strip()
        if not text:
            return _RenderedInline("")
        cues: list[EmphasisCue] = []
        for cue in rendered.cues:
            start = max(0, cue.start - leading)
            end = min(len(text), cue.end - leading)
            if start < end:
                cues.append(EmphasisCue(start=start, end=end, kind=cue.kind))
        return _RenderedInline(text=text, cues=tuple(cues))
