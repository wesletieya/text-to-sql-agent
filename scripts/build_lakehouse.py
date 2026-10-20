"""Build the Olist lakehouse: bronze (raw) -> silver (clean) -> gold (star schema)."""

import os
from pathlib import Path

import duckdb

LAKE_PATH = Path(os.environ.get("LAKE_PATH", "data/lake.duckdb"))
RAW_DIR = Path("data/raw/olist")

BRONZE_TABLES = {
    "customers": "olist_customers_dataset.csv",
    "geolocation": "olist_geolocation_dataset.csv",
    "order_items": "olist_order_items_dataset.csv",
    "order_payments": "olist_order_payments_dataset.csv",
    "order_reviews": "olist_order_reviews_dataset.csv",
    "orders": "olist_orders_dataset.csv",
    "products": "olist_products_dataset.csv",
    "sellers": "olist_sellers_dataset.csv",
    "category_translation": "product_category_name_translation.csv",
}


def build_bronze(con: duckdb.DuckDBPyConnection, raw_dir: Path = RAW_DIR) -> None:
    """Load each raw CSV as-is (all columns as text) into the bronze schema."""
    con.execute("CREATE SCHEMA IF NOT EXISTS bronze")
    for table, filename in BRONZE_TABLES.items():
        path = raw_dir / filename
        if not path.exists():
            raise SystemExit(f"Missing {path}. Run scripts/download_olist.py first.")
        con.execute(
            f"CREATE OR REPLACE TABLE bronze.{table} AS "
            "SELECT * FROM read_csv(?, header = true, all_varchar = true)",
            [str(path)],
        )


def print_summary(con: duckdb.DuckDBPyConnection, schema: str) -> None:
    """Print row counts for every table in schema."""
    tables = con.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = ? ORDER BY table_name",
        [schema],
    ).fetchall()
    for (table,) in tables:
        count = con.execute(f"SELECT count(*) FROM {schema}.{table}").fetchone()[0]
        print(f"{schema}.{table:<22} {count:>10,}")


def main() -> None:
    LAKE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(str(LAKE_PATH)) as con:
        build_bronze(con)
        print_summary(con, "bronze")


if __name__ == "__main__":
    main()
