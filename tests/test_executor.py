"""Tests for agent/executor.py: the read-only, hardened connection is the second line of defense.

These tests call execute() directly, bypassing the validator on purpose.
"""

from collections.abc import Iterator
from pathlib import Path

import duckdb
import pytest

from agent.executor import QueryTimeoutError, connect, execute
from scripts.build_lakehouse import build_bronze, build_gold, build_silver

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "olist"


@pytest.fixture(scope="module")
def lake_file(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("lake") / "lake.duckdb"
    with duckdb.connect(str(path)) as con:
        build_bronze(con, FIXTURES_DIR)
        build_silver(con)
        build_gold(con)
    return path


@pytest.fixture
def con(lake_file: Path) -> Iterator[duckdb.DuckDBPyConnection]:
    connection = connect(lake_file)
    yield connection
    connection.close()


def test_select_returns_columns_and_rows(con: duckdb.DuckDBPyConnection) -> None:
    result = execute(con, "SELECT count(*) AS n FROM gold.fact_orders")
    assert result.columns == ["n"]
    assert result.rows[0][0] > 0
    assert result.truncated is False


def test_rows_are_capped(con: duckdb.DuckDBPyConnection) -> None:
    result = execute(con, "SELECT * FROM gold.dim_date", max_rows=5)
    assert len(result.rows) == 5
    assert result.truncated is True


@pytest.mark.parametrize(
    "sql",
    [
        "CREATE TABLE gold.x AS SELECT 1",
        "DELETE FROM gold.fact_orders",
        "DROP TABLE gold.fact_orders",
    ],
)
def test_connection_cannot_write(con: duckdb.DuckDBPyConnection, sql: str) -> None:
    with pytest.raises(duckdb.Error):
        execute(con, sql)


@pytest.mark.parametrize(
    "sql",
    [
        f"SELECT * FROM read_csv('{FIXTURES_DIR / 'olist_sellers_dataset.csv'}')",
        "ATTACH 'other.duckdb' AS other",
        "INSTALL httpfs",
        "SET enable_external_access = true",
    ],
)
def test_connection_cannot_reach_files_or_change_config(
    con: duckdb.DuckDBPyConnection, sql: str
) -> None:
    with pytest.raises(duckdb.Error):
        execute(con, sql)


def test_long_query_is_interrupted(con: duckdb.DuckDBPyConnection) -> None:
    with pytest.raises(QueryTimeoutError):
        execute(
            con, "SELECT count(*) FROM range(10000000000) AS a(x) WHERE x % 7 = 3", timeout_s=0.5
        )
