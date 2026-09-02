"""Semantic Markdown-to-AST parser without rendering or TTS concerns."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Sequence

from markdown_it import MarkdownIt
from markdown_it.token import Token
from mdit_py_plugins.footnote import footnote_plugin

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
    ListItem,
    Paragraph,
    Strong,
    Table,
    TableCell,
    TableRow,
    Text,
    ThematicBreak,
    inline_text,
)
from markdown_tts.config import ParserRules
from markdown_tts.loader import load_markdown


LOGGER = logging.getLogger(__name__)


class MarkdownParser:
    """Parse Markdown into a semantic, provider-independent document AST."""

    def __init__(self, rules: ParserRules) -> None:
        self._rules = rules
        self._markdown = (
            MarkdownIt("commonmark", {"html": True})
            .enable("table")
            .use(footnote_plugin)
        )

    def parse(self, markdown: str) -> Document:
        """Parse one Markdown document and apply configured non-speech filters."""
        body, front_matter = self._extract_front_matter(markdown)
        tokens = self._markdown.parse(body)
        children, next_index = self._parse_blocks(tokens, 0)
        if next_index != len(tokens):
            LOGGER.warning("Nicht alle Markdown-Tokens wurden verarbeitet: %s/%s", next_index, len(tokens))
        LOGGER.info("Markdown geparst: %s AST-Blöcke", len(children))
        return Document(children=tuple(children), front_matter=front_matter)

    def _extract_front_matter(self, markdown: str) -> tuple[str, str | None]:
        lines = markdown.splitlines(keepends=True)
        delimiter = self._rules.front_matter_delimiter
        if not lines or lines[0].strip() != delimiter:
            return markdown, None

        for index, line in enumerate(lines[1:], start=1):
            if line.strip() == delimiter:
                metadata = "".join(lines[1:index]).strip()
                return "".join(lines[index + 1 :]), metadata

        LOGGER.warning("Frontmatter-Anfang ohne schließenden Trenner; Inhalt bleibt unverändert.")
        return markdown, None

    def _parse_blocks(
        self,
        tokens: Sequence[Token],
        index: int,
        stop_type: str | None = None,
    ) -> tuple[list[BlockNode], int]:
        blocks: list[BlockNode] = []
        while index < len(tokens):
            token = tokens[index]
            if stop_type is not None and token.type == stop_type:
                return blocks, index + 1

            if token.type in {"paragraph_open", "heading_open"}:
                block, index = self._parse_text_block(tokens, index)
                if block is not None:
                    blocks.append(block)
                continue

            if token.type in {"bullet_list_open", "ordered_list_open"}:
                block, index = self._parse_list(tokens, index)
                blocks.append(block)
                continue

            if token.type == "table_open":
                block, index = self._parse_table(tokens, index)
                blocks.append(block)
                continue

            if token.type == "footnote_block_open":
                definitions, index = self._parse_footnote_block(tokens, index)
                blocks.extend(definitions)
                continue

            if token.type == "blockquote_open":
                children, index = self._parse_blocks(tokens, index + 1, "blockquote_close")
                blocks.append(BlockQuote(children=tuple(children)))
                continue

            if token.type in {"fence", "code_block"}:
                language = token.info.strip().split(maxsplit=1)[0] if token.info.strip() else None
                blocks.append(CodeBlock(value=token.content, language=language))
                index += 1
                continue

            if token.type == "hr":
                blocks.append(ThematicBreak())
                index += 1
                continue

            if token.type == "html_block":
                if not (self._rules.remove_html_comments and self._is_html_comment(token.content)):
                    blocks.append(HtmlBlock(value=token.content))
                index += 1
                continue

            LOGGER.debug("Überspringe nicht abbildbares Markdown-Token: %s", token.type)
            index += 1

        if stop_type is not None:
            LOGGER.warning("Erwartetes schließendes Markdown-Token fehlt: %s", stop_type)
        return blocks, index

    def _parse_text_block(
        self, tokens: Sequence[Token], index: int
    ) -> tuple[Paragraph | Heading | None, int]:
        opening = tokens[index]
        inline_index = index + 1
        if inline_index >= len(tokens) or tokens[inline_index].type != "inline":
            LOGGER.warning("Textblock ohne Inline-Inhalt: %s", opening.type)
            return None, index + 1

        inline_token = tokens[inline_index]
        closing_type = "heading_close" if opening.type == "heading_open" else "paragraph_close"
        next_index = inline_index + 1
        if next_index < len(tokens) and tokens[next_index].type == closing_type:
            next_index += 1

        children = tuple(
            self._filter_metadata_lines(self._parse_inline(inline_token.children or []))
        )
        if not inline_text(children).strip():
            return None, next_index

        if opening.type == "heading_open":
            return Heading(level=int(opening.tag[1:]), children=children), next_index
        return Paragraph(children=children), next_index

    def _parse_list(self, tokens: Sequence[Token], index: int) -> tuple[ListBlock, int]:
        opening = tokens[index]
        ordered = opening.type == "ordered_list_open"
        start_value = opening.attrGet("start") if ordered else None
        start = int(start_value) if start_value is not None else (1 if ordered else None)
        close_type = "ordered_list_close" if ordered else "bullet_list_close"
        items: list[ListItem] = []
        index += 1

        while index < len(tokens) and tokens[index].type != close_type:
            if tokens[index].type != "list_item_open":
                LOGGER.debug("Überspringe unerwartetes Listen-Token: %s", tokens[index].type)
                index += 1
                continue
            item_children, index = self._parse_blocks(tokens, index + 1, "list_item_close")
            items.append(ListItem(children=tuple(item_children)))

        if index < len(tokens) and tokens[index].type == close_type:
            index += 1
        else:
            LOGGER.warning("Markdown-Liste ohne schließendes Token: %s", close_type)

        return ListBlock(ordered=ordered, start=start, items=tuple(items)), index

    def _parse_table(self, tokens: Sequence[Token], index: int) -> tuple[Table, int]:
        rows: list[TableRow] = []
        index += 1
        while index < len(tokens) and tokens[index].type != "table_close":
            if tokens[index].type != "tr_open":
                index += 1
                continue

            cells: list[TableCell] = []
            index += 1
            while index < len(tokens) and tokens[index].type != "tr_close":
                opening = tokens[index]
                if opening.type not in {"th_open", "td_open"}:
                    index += 1
                    continue

                inline_index = index + 1
                inline_tokens: Sequence[Token] = []
                if inline_index < len(tokens) and tokens[inline_index].type == "inline":
                    inline_tokens = tokens[inline_index].children or []
                    index = inline_index + 1
                else:
                    index += 1

                close_type = "th_close" if opening.type == "th_open" else "td_close"
                while index < len(tokens) and tokens[index].type != close_type:
                    index += 1
                if index < len(tokens):
                    index += 1

                cells.append(
                    TableCell(
                        header=opening.type == "th_open",
                        children=tuple(self._parse_inline(inline_tokens)),
                    )
                )

            if index < len(tokens) and tokens[index].type == "tr_close":
                index += 1
            rows.append(TableRow(cells=tuple(cells)))

        if index < len(tokens) and tokens[index].type == "table_close":
            index += 1
        else:
            LOGGER.warning("Markdown-Tabelle ohne schließendes Token.")
        return Table(rows=tuple(rows)), index

    def _parse_footnote_block(
        self, tokens: Sequence[Token], index: int
    ) -> tuple[list[FootnoteDefinition], int]:
        definitions: list[FootnoteDefinition] = []
        index += 1
        while index < len(tokens) and tokens[index].type != "footnote_block_close":
            opening = tokens[index]
            if opening.type != "footnote_open":
                index += 1
                continue
            label = str(opening.meta.get("label", opening.meta.get("id", "")))
            children, index = self._parse_blocks(tokens, index + 1, "footnote_close")
            definitions.append(FootnoteDefinition(label=label, children=tuple(children)))

        if index < len(tokens) and tokens[index].type == "footnote_block_close":
            index += 1
        else:
            LOGGER.warning("Fußnotenblock ohne schließendes Token.")
        return definitions, index

    def _parse_inline(self, tokens: Sequence[Token]) -> list[InlineNode]:
        children, _ = self._parse_inline_until(tokens, 0, None)
        return children

    def _parse_inline_until(
        self,
        tokens: Sequence[Token],
        index: int,
        stop_type: str | None,
    ) -> tuple[list[InlineNode], int]:
        nodes: list[InlineNode] = []
        while index < len(tokens):
            token = tokens[index]
            if stop_type is not None and token.type == stop_type:
                return nodes, index + 1

            if token.type == "text":
                cleaned = self._clean_text(token.content)
                if cleaned:
                    nodes.append(Text(cleaned))
                index += 1
                continue

            if token.type == "code_inline":
                nodes.append(InlineCode(token.content))
                index += 1
                continue

            container_types = {
                "em_open": ("em_close", Emphasis),
                "strong_open": ("strong_close", Strong),
                "link_open": ("link_close", Link),
            }
            if token.type in container_types:
                closing, node_type = container_types[token.type]
                nested, index = self._parse_inline_until(tokens, index + 1, closing)
                if inline_text(tuple(nested)).strip():
                    nodes.append(node_type(tuple(nested)))
                continue

            if token.type == "image":
                alt_text = self._clean_text(token.content)
                if alt_text:
                    nodes.append(Image(alt_text=alt_text))
                index += 1
                continue

            if token.type == "footnote_ref":
                label = str(token.meta.get("label", token.meta.get("id", "")))
                nodes.append(FootnoteReference(label=label))
                index += 1
                continue

            if token.type in {"softbreak", "hardbreak"}:
                nodes.append(LineBreak(hard=token.type == "hardbreak"))
                index += 1
                continue

            if token.type == "html_inline" and self._rules.remove_html_comments:
                if self._is_html_comment(token.content):
                    index += 1
                    continue

            if token.content:
                cleaned = self._clean_text(token.content)
                if cleaned:
                    nodes.append(Text(cleaned))
            index += 1

        return nodes, index

    def _clean_text(self, text: str) -> str:
        if not self._rules.remove_urls:
            return text
        return self._rules.url_pattern.sub("", text)

    def _filter_metadata_lines(self, nodes: list[InlineNode]) -> list[InlineNode]:
        lines: list[tuple[list[InlineNode], LineBreak | None]] = []
        current: list[InlineNode] = []
        for node in nodes:
            if isinstance(node, LineBreak):
                lines.append((current, node))
                current = []
            else:
                current.append(node)
        lines.append((current, None))

        result: list[InlineNode] = []
        separator_after_last_kept: LineBreak | None = None
        for line, separator in lines:
            if self._is_filtered_metadata_line(inline_text(tuple(line))):
                continue
            if result and separator_after_last_kept is not None:
                result.append(separator_after_last_kept)
            result.extend(line)
            separator_after_last_kept = separator
        return result

    def _is_filtered_metadata_line(self, text: str) -> bool:
        stripped = text.lstrip()
        if any(stripped.startswith(prefix) for prefix in self._rules.source_prefixes):
            return True
        return self._rules.date_line_pattern.fullmatch(stripped) is not None

    @staticmethod
    def _is_html_comment(value: str) -> bool:
        return value.lstrip().startswith("<!--") and value.rstrip().endswith("-->")


def parse_file(path: str | Path, rules: ParserRules) -> Document:
    """Load and parse one Markdown file using explicit parser rules."""
    return MarkdownParser(rules).parse(load_markdown(path))
