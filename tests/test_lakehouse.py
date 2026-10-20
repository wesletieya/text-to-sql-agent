"""Data quality tests for the lakehouse, built from the committed Olist sample."""

import duckdb
import pytest

PRIMARY_KEYS = [
    ("silver.geolocation", ["zip_code_prefix"]),
    ("gold.dim_customer", ["customer_unique_id"]),
    ("gold.dim_seller", ["seller_id"]),
    ("gold.dim_product", ["product_id"]),
    ("gold.dim_date", ["date"]),
    ("gold.fact_orders", ["order_id"]),
    ("gold.fact_order_items", ["order_id", "order_item_id"]),
    ("gold.fact_payments", ["order_id", "payment_sequential"]),
    ("gold.fact_reviews", ["review_id", "order_id"]),
]

FOREIGN_KEYS = [
    ("gold.fact_orders", "customer_unique_id", "gold.dim_customer", "customer_unique_id"),
    ("gold.fact_orders", "purchase_date", "gold.dim_date", "date"),
    ("gold.fact_order_items", "order_id", "gold.fact_orders", "order_id"),
    ("gold.fact_order_items", "product_id", "gold.dim_product", "product_id"),
    ("gold.fact_order_items", "seller_id", "gold.dim_seller", "seller_id"),
    ("gold.fact_payments", "order_id", "gold.fact_orders", "order_id"),
    ("gold.fact_reviews", "order_id", "gold.fact_orders", "order_id"),
]


def scalar(con: duckdb.DuckDBPyConnection, sql: str) -> object:
    return con.execute(sql).fetchone()[0]


@pytest.mark.parametrize(("table", "columns"), PRIMARY_KEYS)
def test_primary_key_is_unique_and_not_null(
    lake: duckdb.DuckDBPyConnection, table: str, columns: list[str]
) -> None:
    key = ", ".join(columns)
    not_null = " AND ".join(f"{col} IS NOT NULL" for col in columns)
    assert scalar(lake, f"SELECT count(*) FROM {table} WHERE NOT ({not_null})") == 0
    duplicates = scalar(
        lake, f"SELECT count(*) FROM (SELECT {key} FROM {table} GROUP BY {key} HAVING count(*) > 1)"
    )
    assert duplicates == 0


@pytest.mark.parametrize(("child", "fk", "parent", "pk"), FOREIGN_KEYS)
def test_no_orphan_foreign_keys(
    lake: duckdb.DuckDBPyConnection, child: str, fk: str, parent: str, pk: str
) -> None:
    orphans = scalar(
        lake,
        f"SELECT count(*) FROM {child} AS c LEFT JOIN {parent} AS p ON c.{fk} = p.{pk} "
        f"WHERE c.{fk} IS NOT NULL AND p.{pk} IS NULL",
    )
    assert orphans == 0


def test_dim_customer_has_one_row_per_person(lake: duckdb.DuckDBPyConnection) -> None:
    people = scalar(lake, "SELECT count(DISTINCT customer_unique_id) FROM silver.customers")
    assert scalar(lake, "SELECT count(*) FROM gold.dim_customer") == people


def test_sample_contains_a_repeat_customer(lake: duckdb.DuckDBPyConnection) -> None:
    repeat = scalar(
        lake,
        "SELECT count(*) FROM (SELECT customer_unique_id FROM gold.fact_orders "
        "GROUP BY 1 HAVING count(*) >= 2)",
    )
    assert repeat >= 1


def test_delivery_metrics_only_for_delivered_orders_with_a_date(
    lake: duckdb.DuckDBPyConnection,
) -> None:
    wrongly_filled = scalar(
        lake,
        "SELECT count(*) FROM gold.fact_orders "
        "WHERE (delivery_days IS NOT NULL OR is_late IS NOT NULL) "
        "AND (order_status <> 'delivered' OR delivered_customer_at IS NULL)",
    )
    assert wrongly_filled == 0


def test_delivered_without_date_keeps_null_delivery_days(
    lake: duckdb.DuckDBPyConnection,
) -> None:
    kept_null = scalar(
        lake,
        "SELECT count(*) FROM gold.fact_orders "
        "WHERE order_status = 'delivered' AND delivered_customer_at IS NULL "
        "AND delivery_days IS NULL",
    )
    assert kept_null >= 1


def test_delivery_days_are_not_negative(lake: duckdb.DuckDBPyConnection) -> None:
    assert scalar(lake, "SELECT count(*) FROM gold.fact_orders WHERE delivery_days < 0") == 0


def test_order_totals_do_not_fan_out(lake: duckdb.DuckDBPyConnection) -> None:
    from_orders = scalar(lake, "SELECT sum(items_value) FROM gold.fact_orders")
    from_items = scalar(lake, "SELECT sum(price) FROM gold.fact_order_items")
    assert from_orders == from_items


def test_every_product_has_an_english_category(lake: duckdb.DuckDBPyConnection) -> None:
    assert scalar(lake, "SELECT count(*) FROM gold.dim_product WHERE category_en IS NULL") == 0
    assert scalar(lake, "SELECT count(*) FROM gold.dim_product WHERE category_en = 'unknown'") >= 1
    assert scalar(lake, "SELECT count(*) FROM gold.dim_product WHERE category_en = 'pc_gamer'") >= 1
