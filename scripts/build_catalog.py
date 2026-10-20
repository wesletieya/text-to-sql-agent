"""Generate semantic/catalog.yaml from the lakehouse, keeping hand-written descriptions.

Types, row counts and sample values are refreshed from the database on every run.
Descriptions, joins and the glossary are written by hand and are never overwritten.
"""

import os
from pathlib import Path
from typing import Any

import duckdb
import yaml

LAKE_PATH = Path(os.environ.get("LAKE_PATH", "data/lake.duckdb"))
CATALOG_PATH = Path("semantic/catalog.yaml")
SCHEMAS = ("gold", "tpch")
MAX_SAMPLE_VALUES = 80
# Never sample identifiers (not categories) nor free text written by users (untrusted data).
NO_SAMPLE_SUFFIXES = ("_id", "_title", "_message", "_comment", "comment")

Catalog = dict[str, Any]


def sample_values(con: duckdb.DuckDBPyConnection, table: str, column: str) -> list[str] | None:
    """Return the distinct values of a text column if it is categorical, else None."""
    if column.endswith(NO_SAMPLE_SUFFIXES):
        return None
    distinct = con.execute(f'SELECT count(DISTINCT "{column}") FROM {table}').fetchone()[0]
    if distinct == 0 or distinct > MAX_SAMPLE_VALUES:
        return None
    rows = con.execute(
        f'SELECT "{column}" FROM {table} WHERE "{column}" IS NOT NULL '
        f"GROUP BY 1 ORDER BY count(*) DESC, 1"
    ).fetchall()
    return [value for (value,) in rows]


def introspect(con: duckdb.DuckDBPyConnection, schemas: tuple[str, ...] = SCHEMAS) -> Catalog:
    """Read tables, columns, types, row counts and categorical values from the database."""
    tables: Catalog = {}
    columns = con.execute(
        "SELECT table_schema, table_name, column_name, data_type "
        "FROM information_schema.columns "
        f"WHERE table_schema IN ({', '.join('?' for _ in schemas)}) "
        "ORDER BY table_schema, table_name, ordinal_position",
        list(schemas),
    ).fetchall()
    for schema, table_name, column, data_type in columns:
        table = f"{schema}.{table_name}"
        if table not in tables:
            row_count = con.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            tables[table] = {"row_count": row_count, "columns": {}}
        entry: dict[str, Any] = {"type": data_type}
        if data_type == "VARCHAR":
            values = sample_values(con, table, column)
            if values is not None:
                entry["sample_values"] = values
        tables[table]["columns"][column] = entry
    return tables


def merge(generated: Catalog, existing: Catalog) -> Catalog:
    """Combine fresh database metadata with the hand-written parts of the existing catalog."""
    old_tables = existing.get("tables") or {}
    tables: Catalog = {}
    for table, meta in generated.items():
        old_table = old_tables.get(table) or {}
        old_columns = old_table.get("columns") or {}
        columns: Catalog = {}
        for column, col_meta in meta["columns"].items():
            description = (old_columns.get(column) or {}).get("description", "")
            columns[column] = {"description": description, **col_meta}
        tables[table] = {
            "description": old_table.get("description", ""),
            "row_count": meta["row_count"],
            "columns": columns,
        }
    return {
        "tables": tables,
        "joins": existing.get("joins") or [],
        "glossary": existing.get("glossary") or {},
    }


def missing_descriptions(catalog: Catalog) -> list[str]:
    """List tables and columns that still have no description."""
    missing = []
    for table, meta in catalog["tables"].items():
        if not meta["description"]:
            missing.append(table)
        missing += [f"{table}.{c}" for c, m in meta["columns"].items() if not m["description"]]
    return missing


def main() -> None:
    existing = (
        yaml.safe_load(CATALOG_PATH.read_text(encoding="utf-8")) if CATALOG_PATH.exists() else {}
    )
    with duckdb.connect(str(LAKE_PATH), read_only=True) as con:
        catalog = merge(introspect(con), existing or {})
    CATALOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CATALOG_PATH.write_text(
        yaml.safe_dump(catalog, sort_keys=False, allow_unicode=True, width=100), encoding="utf-8"
    )
    missing = missing_descriptions(catalog)
    print(f"Wrote {CATALOG_PATH}: {len(catalog['tables'])} tables.")
    if missing:
        print(f"{len(missing)} items without description, e.g. {', '.join(missing[:5])}")


if __name__ == "__main__":
    main()
