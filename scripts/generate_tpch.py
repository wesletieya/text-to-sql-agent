"""Generate the TPC-H benchmark data into the tpch schema of the lakehouse."""

import os
from pathlib import Path

import duckdb

LAKE_PATH = Path(os.environ.get("LAKE_PATH", "data/lake.duckdb"))
SCHEMA = "tpch"
SCALE_FACTOR = 0.1


def tpch_exists(con: duckdb.DuckDBPyConnection) -> bool:
    """Return True if the TPC-H tables are already generated."""
    row = con.execute(
        "SELECT count(*) FROM information_schema.tables "
        "WHERE table_schema = ? AND table_name = 'lineitem'",
        [SCHEMA],
    ).fetchone()
    return row[0] > 0


def generate(con: duckdb.DuckDBPyConnection) -> None:
    """Generate TPC-H tables into SCHEMA."""
    con.execute("INSTALL tpch")
    con.execute("LOAD tpch")
    con.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
    con.execute(f"CALL dbgen(sf = {SCALE_FACTOR}, schema = '{SCHEMA}')")


def print_summary(con: duckdb.DuckDBPyConnection) -> None:
    """Print row counts for every table in SCHEMA."""
    tables = con.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = ? ORDER BY table_name",
        [SCHEMA],
    ).fetchall()
    for (table,) in tables:
        count = con.execute(f"SELECT count(*) FROM {SCHEMA}.{table}").fetchone()[0]
        print(f"{SCHEMA}.{table:<10} {count:>10,}")


def main() -> None:
    LAKE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(str(LAKE_PATH)) as con:
        if tpch_exists(con):
            print(f"TPC-H already present in {LAKE_PATH}, skipping generation.")
        else:
            print(f"Generating TPC-H (sf={SCALE_FACTOR}) into {LAKE_PATH}...")
            generate(con)
        print_summary(con)


if __name__ == "__main__":
    main()
