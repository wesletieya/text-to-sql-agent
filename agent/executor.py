"""Execute validated SQL on a hardened, read-only DuckDB connection.

This is the second line of defense: even if the validator let something through,
the connection cannot write, read files, attach databases or load extensions.
"""

import threading
import time
from pathlib import Path
from typing import Any

import duckdb
from pydantic import BaseModel

DEFAULT_TIMEOUT_S = 10.0
DEFAULT_MAX_ROWS = 1000

HARDENED_CONFIG = {
    "enable_external_access": False,
    "autoinstall_known_extensions": False,
    "autoload_known_extensions": False,
    "lock_configuration": True,
}


class QueryTimeoutError(RuntimeError):
    """Raised when a query runs longer than the allowed time."""


class QueryResult(BaseModel):
    columns: list[str]
    rows: list[list[Any]]
    truncated: bool
    elapsed_ms: float


def connect(lake_path: Path) -> duckdb.DuckDBPyConnection:
    """Open the lakehouse read-only, without file, network or extension access."""
    return duckdb.connect(str(lake_path), read_only=True, config=HARDENED_CONFIG)


def execute(
    con: duckdb.DuckDBPyConnection,
    sql: str,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    max_rows: int = DEFAULT_MAX_ROWS,
) -> QueryResult:
    """Run sql, interrupting it after timeout_s and returning at most max_rows rows."""
    timer = threading.Timer(timeout_s, con.interrupt)
    start = time.perf_counter()
    timer.start()
    try:
        cursor = con.execute(sql)
        rows = cursor.fetchmany(max_rows + 1)
    except duckdb.InterruptException as error:
        raise QueryTimeoutError(f"Query exceeded {timeout_s} s") from error
    finally:
        timer.cancel()
    elapsed_ms = (time.perf_counter() - start) * 1000
    columns = [description[0] for description in cursor.description]
    return QueryResult(
        columns=columns,
        rows=[list(row) for row in rows[:max_rows]],
        truncated=len(rows) > max_rows,
        elapsed_ms=round(elapsed_ms, 1),
    )
