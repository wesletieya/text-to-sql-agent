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
SILVER_TABLES = {
    "customers": """
        SELECT
            customer_id,
            customer_unique_id,
            customer_zip_code_prefix AS zip_code_prefix,
            customer_city AS city,
            upper(customer_state) AS state
        FROM bronze.customers
    """,
    "sellers": """
        SELECT
            seller_id,
            seller_zip_code_prefix AS zip_code_prefix,
            seller_city AS city,
            upper(seller_state) AS state
        FROM bronze.sellers
    """,
    "geolocation": """
        SELECT
            geolocation_zip_code_prefix AS zip_code_prefix,
            avg(CAST(geolocation_lat AS DOUBLE)) AS lat,
            avg(CAST(geolocation_lng AS DOUBLE)) AS lng
        FROM bronze.geolocation
        GROUP BY geolocation_zip_code_prefix
    """,
    "orders": """
        SELECT
            order_id,
            customer_id,
            order_status,
            CAST(order_purchase_timestamp AS TIMESTAMP) AS purchased_at,
            CAST(order_approved_at AS TIMESTAMP) AS approved_at,
            CAST(order_delivered_carrier_date AS TIMESTAMP) AS delivered_carrier_at,
            CAST(order_delivered_customer_date AS TIMESTAMP) AS delivered_customer_at,
            CAST(order_estimated_delivery_date AS TIMESTAMP) AS estimated_delivery_at
        FROM bronze.orders
    """,
    "order_items": """
        SELECT
            order_id,
            CAST(order_item_id AS INTEGER) AS order_item_id,
            product_id,
            seller_id,
            CAST(shipping_limit_date AS TIMESTAMP) AS shipping_limit_at,
            CAST(price AS DECIMAL(10, 2)) AS price,
            CAST(freight_value AS DECIMAL(10, 2)) AS freight_value
        FROM bronze.order_items
    """,
    "order_payments": """
        SELECT
            order_id,
            CAST(payment_sequential AS INTEGER) AS payment_sequential,
            payment_type,
            CAST(payment_installments AS INTEGER) AS installments,
            CAST(payment_value AS DECIMAL(10, 2)) AS payment_value
        FROM bronze.order_payments
    """,
    "order_reviews": """
        SELECT
            review_id,
            order_id,
            CAST(review_score AS INTEGER) AS score,
            review_comment_title AS comment_title,
            review_comment_message AS comment_message,
            CAST(review_creation_date AS TIMESTAMP) AS created_at,
            CAST(review_answer_timestamp AS TIMESTAMP) AS answered_at
        FROM bronze.order_reviews
    """,
    "products": """
        SELECT
            product_id,
            product_category_name AS category_name,
            CAST(product_name_lenght AS INTEGER) AS name_length,
            CAST(product_description_lenght AS INTEGER) AS description_length,
            CAST(product_photos_qty AS INTEGER) AS photos_qty,
            CAST(product_weight_g AS INTEGER) AS weight_g,
            CAST(product_length_cm AS INTEGER) AS length_cm,
            CAST(product_height_cm AS INTEGER) AS height_cm,
            CAST(product_width_cm AS INTEGER) AS width_cm
        FROM bronze.products
    """,
    "category_translation": """
        SELECT
            product_category_name AS category_name,
            product_category_name_english AS category_name_en
        FROM bronze.category_translation
    """,
}

GOLD_TABLES = {
    "dim_customer": """
        SELECT
            c.customer_unique_id,
            arg_max(c.zip_code_prefix, o.purchased_at) AS zip_code_prefix,
            arg_max(c.city, o.purchased_at) AS city,
            arg_max(c.state, o.purchased_at) AS state
        FROM silver.customers AS c
        JOIN silver.orders AS o USING (customer_id)
        GROUP BY c.customer_unique_id
    """,
    "dim_seller": """
        SELECT seller_id, zip_code_prefix, city, state
        FROM silver.sellers
    """,
    "dim_product": """
        SELECT
            p.product_id,
            coalesce(p.category_name, 'unknown') AS category_pt,
            coalesce(t.category_name_en, p.category_name, 'unknown') AS category_en,
            p.photos_qty,
            p.weight_g,
            p.length_cm,
            p.height_cm,
            p.width_cm
        FROM silver.products AS p
        LEFT JOIN silver.category_translation AS t USING (category_name)
    """,
    "dim_date": """
        SELECT
            CAST(d AS DATE) AS date,
            year(d) AS year,
            quarter(d) AS quarter,
            month(d) AS month,
            monthname(d) AS month_name,
            day(d) AS day,
            isodow(d) AS day_of_week,
            dayname(d) AS day_name,
            isodow(d) >= 6 AS is_weekend
        FROM generate_series(DATE '2016-01-01', DATE '2018-12-31', INTERVAL 1 DAY) AS t(d)
    """,
    "fact_orders": """
        SELECT
            o.order_id,
            c.customer_unique_id,
            o.order_status,
            o.purchased_at,
            CAST(o.purchased_at AS DATE) AS purchase_date,
            o.approved_at,
            o.delivered_carrier_at,
            o.delivered_customer_at,
            o.estimated_delivery_at,
            CASE WHEN o.order_status = 'delivered' AND o.delivered_customer_at IS NOT NULL
                THEN date_diff('day', o.purchased_at, o.delivered_customer_at)
            END AS delivery_days,
            CASE WHEN o.order_status = 'delivered' AND o.delivered_customer_at IS NOT NULL
                THEN CAST(o.delivered_customer_at AS DATE) > CAST(o.estimated_delivery_at AS DATE)
            END AS is_late,
            coalesce(i.items_count, 0) AS items_count,
            coalesce(i.items_value, 0) AS items_value,
            coalesce(i.freight_value, 0) AS freight_value
        FROM silver.orders AS o
        JOIN silver.customers AS c USING (customer_id)
        LEFT JOIN (
            SELECT
                order_id,
                count(*) AS items_count,
                sum(price) AS items_value,
                sum(freight_value) AS freight_value
            FROM silver.order_items
            GROUP BY order_id
        ) AS i USING (order_id)
    """,
    "fact_order_items": """
        SELECT
            order_id, order_item_id, product_id, seller_id, shipping_limit_at, price, freight_value
        FROM silver.order_items
    """,
    "fact_payments": """
        SELECT order_id, payment_sequential, payment_type, installments, payment_value
        FROM silver.order_payments
    """,
    "fact_reviews": """
        SELECT review_id, order_id, score, comment_title, comment_message, created_at, answered_at
        FROM silver.order_reviews
    """,
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
def build_silver(con: duckdb.DuckDBPyConnection) -> None:
    """Clean bronze into typed, consistently named tables in the silver schema."""
    con.execute("CREATE SCHEMA IF NOT EXISTS silver")
    for table, query in SILVER_TABLES.items():
        con.execute(f"CREATE OR REPLACE TABLE silver.{table} AS {query}")

def build_gold(con: duckdb.DuckDBPyConnection) -> None:
    """Build the star schema (dimensions and facts) in the gold schema."""
    con.execute("CREATE SCHEMA IF NOT EXISTS gold")
    for table, query in GOLD_TABLES.items():
        con.execute(f"CREATE OR REPLACE TABLE gold.{table} AS {query}")

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
        build_silver(con)
        print_summary(con, "silver")
        build_gold(con)
        print_summary(con, "gold")




if __name__ == "__main__":
    main()
