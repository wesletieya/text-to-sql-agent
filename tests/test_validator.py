"""Attack and legitimate-query tests for agent/validator.py."""

from pathlib import Path

import pytest
import sqlglot
import yaml

from agent.validator import ValidationError, schema_from_catalog, validate

ROOT = Path(__file__).parent.parent
SCHEMA = schema_from_catalog(
    yaml.safe_load((ROOT / "semantic/catalog.yaml").read_text(encoding="utf-8"))
)
FEWSHOT = yaml.safe_load((ROOT / "semantic/fewshot.yaml").read_text(encoding="utf-8"))["examples"]

ATTACKS = {
    "drop": "DROP TABLE gold.fact_orders",
    "delete": "DELETE FROM gold.fact_orders",
    "update": "UPDATE gold.fact_orders SET order_status = 'x'",
    "insert": "INSERT INTO gold.dim_seller VALUES ('a', 'b', 'c', 'd')",
    "create": "CREATE TABLE gold.x AS SELECT 1",
    "alter": "ALTER TABLE gold.fact_orders ADD COLUMN x INTEGER",
    "multi_statement": "SELECT 1; DROP TABLE gold.fact_orders",
    "multi_statement_delete": "SELECT count(*) FROM gold.fact_orders; DELETE FROM gold.fact_orders",
    "comment_hides_statement": "SELECT 1 -- harmless\n; DROP TABLE gold.fact_orders",
    "block_comment_then_statement": "SELECT 1 /* ok */; DROP TABLE gold.fact_orders",
    "copy": "COPY gold.fact_orders TO 'out.csv'",
    "attach": "ATTACH 'other.duckdb' AS other",
    "install": "INSTALL httpfs",
    "load": "LOAD httpfs",
    "pragma": "PRAGMA database_list",
    "set": "SET enable_external_access = true",
    "call": "CALL dbgen(sf = 1)",
    "export": "EXPORT DATABASE 'dump'",
    "read_csv_passwd": "SELECT * FROM read_csv('/etc/passwd')",
    "read_csv_auto_env": "SELECT * FROM read_csv_auto('C:/Users/me/.env')",
    "read_parquet_s3": "SELECT * FROM read_parquet('s3://bucket/x.parquet')",
    "read_text": "SELECT read_text('.env')",
    "read_blob": "SELECT content FROM read_blob('kaggle.json')",
    "read_json": "SELECT * FROM read_json('x.json')",
    "glob": "SELECT * FROM glob('*')",
    "file_path_as_table": "SELECT * FROM '/etc/passwd'",
    "url_as_table": "SELECT * FROM 'https://evil.example/data.parquet'",
    "duckdb_metadata": "SELECT * FROM duckdb_tables()",
    "getenv": "SELECT getenv('ANTHROPIC_API_KEY')",
    "trapped_cte": "WITH x AS (SELECT * FROM read_csv('/etc/passwd')) SELECT * FROM x",
    "trapped_cte_shadowing": "WITH fact_orders AS (SELECT * FROM 'secret.csv') "
    "SELECT * FROM fact_orders",
    "function_in_subquery": "SELECT * FROM gold.fact_orders WHERE order_id IN "
    "(SELECT column0 FROM read_csv('ids.csv'))",
    "unknown_table": "SELECT * FROM gold.secret_table",
    "information_schema": "SELECT * FROM information_schema.tables",
    "silver_layer": "SELECT * FROM silver.orders",
    "unqualified_table": "SELECT * FROM fact_orders",
    "database_prefix": "SELECT * FROM other_db.gold.fact_orders",
    "invented_column": "SELECT password FROM gold.dim_customer",
    "invented_column_in_where": "SELECT order_id FROM gold.fact_orders WHERE is_vip = true",
    "non_literal_limit": "SELECT order_id FROM gold.fact_orders LIMIT (SELECT 10)",
    "empty": "",
    "syntax_error": "SELEC * FRM gold.fact_orders",
}

LEGITIMATE = {
    "simple": "SELECT order_id FROM gold.fact_orders",
    "cte": "WITH t AS (SELECT customer_unique_id, count(*) AS n FROM gold.fact_orders "
    "GROUP BY customer_unique_id) SELECT * FROM t WHERE n > 1",
    "window": "SELECT order_id, row_number() OVER "
    "(PARTITION BY customer_unique_id ORDER BY purchased_at) AS rn FROM gold.fact_orders",
    "union": "SELECT state FROM gold.dim_customer UNION SELECT state FROM gold.dim_seller",
    "subquery": "SELECT order_id FROM gold.fact_orders WHERE customer_unique_id IN "
    "(SELECT customer_unique_id FROM gold.dim_customer WHERE state = 'SP')",
    "keyword_in_string": "SELECT count(*) FROM gold.fact_orders WHERE order_status = 'DROP TABLE'",
    "keyword_in_comment": "SELECT count(*) FROM gold.fact_orders /* DELETE everything */",
    "trailing_semicolon": "SELECT count(*) FROM gold.fact_orders;",
    "tpch_join": "SELECT n.n_name, count(*) FROM tpch.customer AS c "
    "JOIN tpch.nation AS n ON n.n_nationkey = c.c_nationkey GROUP BY n.n_name",
    "date_functions": "SELECT date_trunc('month', purchase_date) AS m, count(*) "
    "FROM gold.fact_orders GROUP BY m",
}


@pytest.mark.parametrize("sql", ATTACKS.values(), ids=ATTACKS.keys())
def test_attack_is_blocked(sql: str) -> None:
    with pytest.raises(ValidationError):
        validate(sql, SCHEMA)


@pytest.mark.parametrize("sql", LEGITIMATE.values(), ids=LEGITIMATE.keys())
def test_legitimate_query_is_accepted(sql: str) -> None:
    validate(sql, SCHEMA)


@pytest.mark.parametrize("example", FEWSHOT, ids=lambda e: e["question"])
def test_fewshot_examples_are_accepted(example: dict[str, str]) -> None:
    validate(example["sql"], SCHEMA)


def limit_of(sql: str) -> int:
    return int(sqlglot.parse_one(sql, read="duckdb").args["limit"].expression.this)


def test_limit_is_injected_when_missing() -> None:
    assert limit_of(validate("SELECT order_id FROM gold.fact_orders", SCHEMA, max_rows=50)) == 50


def test_limit_is_capped_when_too_high() -> None:
    sql = "SELECT order_id FROM gold.fact_orders LIMIT 5000"
    assert limit_of(validate(sql, SCHEMA, max_rows=50)) == 50


def test_smaller_limit_is_kept() -> None:
    sql = "SELECT order_id FROM gold.fact_orders LIMIT 10"
    assert limit_of(validate(sql, SCHEMA, max_rows=50)) == 10


def test_limit_is_injected_on_union() -> None:
    sql = "SELECT state FROM gold.dim_customer UNION SELECT state FROM gold.dim_seller"
    assert limit_of(validate(sql, SCHEMA, max_rows=50)) == 50
