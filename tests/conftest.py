"""Shared pytest fixtures."""

from collections.abc import Iterator
from pathlib import Path

import duckdb
import pytest

from scripts.build_lakehouse import build_bronze, build_gold, build_silver

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "olist"


@pytest.fixture(scope="session")
def lake() -> Iterator[duckdb.DuckDBPyConnection]:
    """Build bronze, silver and gold from the committed Olist sample, in memory."""
    with duckdb.connect() as con:
        build_bronze(con, FIXTURES_DIR)
        build_silver(con)
        build_gold(con)
        yield con
