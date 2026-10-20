"""Turn semantic/catalog.yaml into the schema description sent to the LLM.

Phase 4 sends the whole catalog. Top-k retrieval of relevant tables can come later.
"""

from pathlib import Path
from typing import Any

import yaml

CATALOG_PATH = Path("semantic/catalog.yaml")
FEWSHOT_PATH = Path("semantic/fewshot.yaml")


def load_catalog(path: Path = CATALOG_PATH) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def load_fewshot(path: Path = FEWSHOT_PATH) -> list[dict[str, str]]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))["examples"]


def render_column(name: str, meta: dict[str, Any]) -> str:
    line = f"  - {name} ({meta['type']})"
    if meta.get("description"):
        line += f": {meta['description']}"
    if meta.get("sample_values"):
        values = ", ".join(repr(value) for value in meta["sample_values"])
        line += f" Values: {values}."
    return line


def render_schema(catalog: dict[str, Any], tables: list[str] | None = None) -> str:
    """Render the tables (all by default), their joins and the glossary as compact text."""
    selected = tables or list(catalog["tables"])
    lines = ["# Tables"]
    for table in selected:
        meta = catalog["tables"][table]
        lines.append(f"\n## {table} ({meta['row_count']:,} rows)")
        if meta.get("description"):
            lines.append(meta["description"])
        lines += [render_column(name, col) for name, col in meta["columns"].items()]

    joins = [join for join in catalog.get("joins", []) if any(join.count(t) for t in selected)]
    if joins:
        lines.append("\n# Joins")
        lines += [f"- {join}" for join in joins]

    if catalog.get("glossary"):
        lines.append("\n# Business glossary (always apply these definitions)")
        for term, entry in catalog["glossary"].items():
            line = f"- {term}: {entry['definition']}"
            if entry.get("sql"):
                line += f" SQL: {entry['sql']}"
            lines.append(line)
    return "\n".join(lines)


def render_fewshot(examples: list[dict[str, str]]) -> str:
    blocks = [f"Question: {e['question']}\nSQL:\n{e['sql'].strip()}" for e in examples]
    return "\n\n".join(blocks)
