"""Extract a small, consistent Olist sample into tests/fixtures/olist/ for CI tests.

The sample keeps every known edge case of the dataset (repeat customers, delivered
orders without a delivery date, products without category, multi-payment orders...)
so the lakehouse tests exercise them without needing Kaggle.
"""

from pathlib import Path

import duckdb

from scripts.build_lakehouse import BRONZE_TABLES, RAW_DIR

FIXTURES_DIR = Path("tests/fixtures/olist")
RANDOM_ORDERS = 40

SAMPLE_ORDERS = """
    WITH repeat_customer AS (
        SELECT customer_unique_id FROM customers
        GROUP BY 1 HAVING count(*) >= 2 ORDER BY md5(customer_unique_id) LIMIT 1
    ),
    picked AS (
        -- delivered orders without a delivery date
        (SELECT order_id FROM orders
         WHERE order_status = 'delivered' AND order_delivered_customer_date IS NULL
         ORDER BY order_id LIMIT 3)
        UNION
        -- every order of one repeat customer
        (SELECT o.order_id FROM orders AS o JOIN customers AS c USING (customer_id)
         WHERE c.customer_unique_id IN (SELECT customer_unique_id FROM repeat_customer))
        UNION
        -- an order with many payments
        (SELECT order_id FROM order_payments GROUP BY 1 HAVING count(*) >= 5
         ORDER BY order_id LIMIT 1)
        UNION
        -- an order with several items
        (SELECT order_id FROM order_items GROUP BY 1 HAVING count(*) >= 3
         ORDER BY order_id LIMIT 1)
        UNION
        -- an order with a product without category
        (SELECT i.order_id FROM order_items AS i JOIN products AS p USING (product_id)
         WHERE p.product_category_name IS NULL ORDER BY i.order_id LIMIT 1)
        UNION
        -- an order with an untranslated category
        (SELECT i.order_id FROM order_items AS i JOIN products AS p USING (product_id)
         WHERE p.product_category_name = 'pc_gamer' ORDER BY i.order_id LIMIT 1)
        UNION
        -- every order covered by one review shared across orders
        (SELECT order_id FROM order_reviews WHERE review_id = (
            SELECT review_id FROM order_reviews GROUP BY 1 HAVING count(*) >= 2
            ORDER BY review_id LIMIT 1))
        UNION
        -- canceled orders
        (SELECT order_id FROM orders WHERE order_status = 'canceled' ORDER BY order_id LIMIT 2)
        UNION
        -- a deterministic pseudo-random sample
        (SELECT order_id FROM orders ORDER BY md5(order_id) LIMIT {random_orders})
    )
    SELECT DISTINCT order_id FROM picked
"""

PICKED = "order_id IN (SELECT order_id FROM picked_orders)"

FILTERS = {
    "orders": PICKED,
    "order_items": PICKED,
    "order_payments": PICKED,
    "order_reviews": PICKED,
    "customers": f"customer_id IN (SELECT customer_id FROM orders WHERE {PICKED})",
    "products": f"product_id IN (SELECT product_id FROM order_items WHERE {PICKED})",
    "sellers": f"seller_id IN (SELECT seller_id FROM order_items WHERE {PICKED})",
    # Keep at most 3 points per zip code: enough to test the silver aggregation.
    "geolocation": f"""geolocation_zip_code_prefix IN (
        SELECT customer_zip_code_prefix FROM customers
        WHERE customer_id IN (SELECT customer_id FROM orders WHERE {PICKED}))
        QUALIFY row_number() OVER (
            PARTITION BY geolocation_zip_code_prefix ORDER BY geolocation_lat) <= 3""",
    "category_translation": "true",
}


def make_fixtures(raw_dir: Path = RAW_DIR, dest: Path = FIXTURES_DIR) -> None:
    """Write a filtered copy of each raw CSV into dest, keeping the original columns."""
    dest.mkdir(parents=True, exist_ok=True)
    with duckdb.connect() as con:
        for table, filename in BRONZE_TABLES.items():
            con.execute(
                f"CREATE TABLE {table} AS "
                "SELECT * FROM read_csv(?, header = true, all_varchar = true)",
                [str(raw_dir / filename)],
            )
        con.execute(
            "CREATE TABLE picked_orders AS " + SAMPLE_ORDERS.format(random_orders=RANDOM_ORDERS)
        )
        for table, filename in BRONZE_TABLES.items():
            con.execute(
                f"CREATE TABLE fixture_{table} AS SELECT * FROM {table} WHERE {FILTERS[table]}"
            )
            con.execute(f"COPY fixture_{table} TO '{dest / filename}' (HEADER, DELIMITER ',')")
            count = con.execute(f"SELECT count(*) FROM fixture_{table}").fetchone()[0]
            print(f"{filename:<42} {count:>6,}")


if __name__ == "__main__":
    make_fixtures()
