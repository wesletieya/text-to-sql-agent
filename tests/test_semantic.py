"""Tests for the semantic layer: catalog generation, catalog content and few-shot examples."""

import os
from pathlib import Path

import duckdb
import pytest
import sqlglot
import yaml

from scripts.build_catalog import introspect, merge, missing_descriptions

ROOT = Path(__file__).parent.parent
CATALOG = yaml.safe_load((ROOT / "semantic/catalog.yaml").read_text(encoding="utf-8"))
FEWSHOT = yaml.safe_load((ROOT / "semantic/fewshot.yaml").read_text(encoding="utf-8"))["examples"]
LAKE_PATH = Path(os.environ.get("LAKE_PATH", ROOT / "data/lake.duckdb"))


def test_merge_keeps_manual_parts_and_refreshes_metadata() -> None:
    existing = {
        "tables": {
            "gold.t": {
                "description": "Hand-written table description.",
                "row_count": 1,
                "columns": {"a": {"description": "Hand-written column.", "type": "INTEGER"}},
            }
        },
        "joins": ["gold.t.a = gold.u.a"],
        "glossary": {"revenue": {"definition": "Hand-written."}},
    }
    generated = {"gold.t": {"row_count": 42, "columns": {"a": {"type": "BIGINT"}}}}

    merged = merge(generated, existing)

    table = merged["tables"]["gold.t"]
    assert table["description"] == "Hand-written table description."
    assert table["row_count"] == 42
    assert table["columns"]["a"] == {"description": "Hand-written column.", "type": "BIGINT"}
    assert merged["joins"] == existing["joins"]
    assert merged["glossary"] == existing["glossary"]


def test_merge_adds_new_columns_and_drops_removed_ones() -> None:
    existing = {"tables": {"gold.t": {"description": "", "columns": {"old": {"description": "x"}}}}}
    generated = {"gold.t": {"row_count": 0, "columns": {"new": {"type": "VARCHAR"}}}}

    columns = merge(generated, existing)["tables"]["gold.t"]["columns"]

    assert columns == {"new": {"description": "", "type": "VARCHAR"}}


def test_introspect_samples_only_categorical_columns(lake: duckdb.DuckDBPyConnection) -> None:
    columns = introspect(lake, ("gold",))["gold.fact_orders"]["columns"]

    assert "delivered" in columns["order_status"]["sample_values"]
    assert "sample_values" not in columns["order_id"]
    reviews = introspect(lake, ("gold",))["gold.fact_reviews"]["columns"]
    assert "sample_values" not in reviews["comment_message"]
    assert columns["items_value"]["type"].startswith("DECIMAL")


def test_catalog_has_no_missing_description() -> None:
    assert missing_descriptions(CATALOG) == []


def test_catalog_joins_reference_existing_columns() -> None:
    for join in CATALOG["joins"]:
        for side in join.split(" = "):
            schema, table, column = side.split(".")
            assert column in CATALOG["tables"][f"{schema}.{table}"]["columns"], side


def test_fewshot_questions_are_unique() -> None:
    questions = [example["question"] for example in FEWSHOT]
    assert len(questions) == len(set(questions))


@pytest.mark.parametrize("example", FEWSHOT, ids=lambda e: e["question"])
def test_fewshot_sql_is_a_single_select(example: dict[str, str]) -> None:
    statements = sqlglot.parse(example["sql"], read="duckdb")
    assert len(statements) == 1
    assert isinstance(statements[0], sqlglot.exp.Query)


@pytest.mark.skipif(not LAKE_PATH.exists(), reason="run `make data` first")
@pytest.mark.parametrize("example", FEWSHOT, ids=lambda e: e["question"])
def test_fewshot_sql_runs_on_full_lake(example: dict[str, str]) -> None:
    with duckdb.connect(str(LAKE_PATH), read_only=True) as con:
        assert con.execute(example["sql"]).fetchall()
