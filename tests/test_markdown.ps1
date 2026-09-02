@'
from pathlib import Path
from pprint import pprint

from markdown_tts import MarkdownParser, ParserRules, load_markdown
from markdown_tts.ast import document_text

rules = ParserRules.from_file("config/parser_rules.json")
markdown = load_markdown(Path("tests/corpus/tc_007_v1.md"))
document = MarkdownParser(rules).parse(markdown)

print("=== AST ===")
pprint(document)

print("\n=== BEREINIGTER ROHTEXT ===")
print(document_text(document))
'@ | uv run python -