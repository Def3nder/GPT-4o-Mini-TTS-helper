"""Language-neutral document model produced by the Markdown parser."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Text:
    value: str


@dataclass(frozen=True, slots=True)
class Emphasis:
    children: tuple[InlineNode, ...]


@dataclass(frozen=True, slots=True)
class Strong:
    children: tuple[InlineNode, ...]


@dataclass(frozen=True, slots=True)
class InlineCode:
    value: str


@dataclass(frozen=True, slots=True)
class Link:
    children: tuple[InlineNode, ...]


@dataclass(frozen=True, slots=True)
class Image:
    alt_text: str


@dataclass(frozen=True, slots=True)
class FootnoteReference:
    label: str


@dataclass(frozen=True, slots=True)
class LineBreak:
    hard: bool


InlineNode = Text | Emphasis | Strong | InlineCode | Link | Image | FootnoteReference | LineBreak


@dataclass(frozen=True, slots=True)
class Paragraph:
    children: tuple[InlineNode, ...]


@dataclass(frozen=True, slots=True)
class Heading:
    level: int
    children: tuple[InlineNode, ...]


@dataclass(frozen=True, slots=True)
class ListItem:
    children: tuple[BlockNode, ...]


@dataclass(frozen=True, slots=True)
class ListBlock:
    ordered: bool
    start: int | None
    items: tuple[ListItem, ...]


@dataclass(frozen=True, slots=True)
class BlockQuote:
    children: tuple[BlockNode, ...]


@dataclass(frozen=True, slots=True)
class CodeBlock:
    value: str
    language: str | None


@dataclass(frozen=True, slots=True)
class ThematicBreak:
    pass


@dataclass(frozen=True, slots=True)
class HtmlBlock:
    value: str


@dataclass(frozen=True, slots=True)
class TableCell:
    header: bool
    children: tuple[InlineNode, ...]


@dataclass(frozen=True, slots=True)
class TableRow:
    cells: tuple[TableCell, ...]


@dataclass(frozen=True, slots=True)
class Table:
    rows: tuple[TableRow, ...]


@dataclass(frozen=True, slots=True)
class FootnoteDefinition:
    label: str
    children: tuple[BlockNode, ...]


BlockNode = (
    Paragraph
    | Heading
    | ListBlock
    | BlockQuote
    | CodeBlock
    | ThematicBreak
    | HtmlBlock
    | Table
    | FootnoteDefinition
)


@dataclass(frozen=True, slots=True)
class Document:
    children: tuple[BlockNode, ...]
    front_matter: str | None = None


def inline_text(nodes: tuple[InlineNode, ...]) -> str:
    """Return the human-visible text represented by inline AST nodes."""
    parts: list[str] = []
    for node in nodes:
        if isinstance(node, (Text, InlineCode)):
            parts.append(node.value)
        elif isinstance(node, (Emphasis, Strong, Link)):
            parts.append(inline_text(node.children))
        elif isinstance(node, Image):
            parts.append(node.alt_text)
        elif isinstance(node, FootnoteReference):
            parts.append(f"[^{node.label}]")
        elif isinstance(node, LineBreak):
            parts.append("\n" if node.hard else " ")
    return "".join(parts)


def block_text(node: BlockNode) -> str:
    """Return visible text for diagnostics and renderer reference tests."""
    if isinstance(node, (Paragraph, Heading)):
        return inline_text(node.children)
    if isinstance(node, ListBlock):
        return "\n".join(block_text(child) for item in node.items for child in item.children)
    if isinstance(node, BlockQuote):
        return "\n".join(block_text(child) for child in node.children)
    if isinstance(node, Table):
        return "\n".join(
            " | ".join(inline_text(cell.children) for cell in row.cells)
            for row in node.rows
        )
    if isinstance(node, FootnoteDefinition):
        content = "\n".join(block_text(child) for child in node.children)
        return f"[^{node.label}]: {content}"
    if isinstance(node, (CodeBlock, HtmlBlock)):
        return node.value
    return ""


def document_text(document: Document) -> str:
    """Return visible text for diagnostics and renderer reference tests."""
    return "\n".join(filter(None, (block_text(child) for child in document.children)))
