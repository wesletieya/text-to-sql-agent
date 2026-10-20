"""Row-count checks on the full lakehouse. Skipped when data/lake.duckdb is absent (CI)."""

import os
from pathlib import Path

import duckdb
import pytest

LAKE_PATH = Path(os.environ.get("LAKE_PATH", "data/lake.duckdb"))

EXPECTED_ROWS = {
    "gold.dim_customer": 96_096,
    "gold.dim_seller": 3_095,
    "gold.dim_product": 32_951,
    "gold.fact_orders": 99_441,
    "gold.fact_order_items": 112_650,
    "gold.fact_payments": 103_886,
    "gold.fact_reviews": 99_224,
    "tpch.lineitem": 600_572,
    "tpch.orders": 150_000,
}

pytestmark = pytest.mark.skipif(not LAKE_PATH.exists(), reason="run `make data` first")


@pytest.mark.parametrize(("table", "expected"), EXPECTED_ROWS.items())
def test_full_lake_row_counts(table: str, expected: int) -> None:
    with duckdb.connect(str(LAKE_PATH), read_only=True) as con:
        assert con.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == expected
