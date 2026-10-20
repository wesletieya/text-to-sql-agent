"""Validate LLM-generated SQL on the sqlglot AST before it reaches the database.

Rules (see CLAUDE.md): exactly one statement, a query only (no DML/DDL/commands),
only allowed schema-qualified tables (CTEs excepted), every column must resolve,
no file or system access functions, and a LIMIT is always present.
"""

from typing import Any

import sqlglot
from sqlglot import exp
from sqlglot.errors import OptimizeError, ParseError
from sqlglot.optimizer.qualify import qualify

DIALECT = "duckdb"
DEFAULT_MAX_ROWS = 1000

# Functions that read files, list directories, reach the network or other databases.
FORBIDDEN_FUNCTIONS = {
    "read_csv",
    "read_csv_auto",
    "read_parquet",
    "parquet_scan",
    "parquet_metadata",
    "parquet_schema",
    "read_json",
    "read_json_auto",
    "read_json_objects",
    "read_ndjson",
    "read_ndjson_auto",
    "read_text",
    "read_blob",
    "read_xlsx",
    "glob",
    "sniff_csv",
    "delta_scan",
    "iceberg_scan",
    "sqlite_scan",
    "sqlite_attach",
    "postgres_scan",
    "postgres_attach",
    "mysql_scan",
    "query",
    "query_table",
    "getenv",
    "load_aws_credentials",
    "httpfs",
}
FORBIDDEN_PREFIXES = ("read_", "duckdb_", "pragma_")

Schema = dict[str, dict[str, dict[str, str]]]


class ValidationError(ValueError):
    """Raised when a SQL query is rejected. The message is safe to show to the LLM."""


def schema_from_catalog(catalog: dict[str, Any]) -> Schema:
    """Convert semantic/catalog.yaml into the {schema: {table: {column: type}}} sqlglot format."""
    schema: Schema = {}
    for full_name, table in catalog["tables"].items():
        db, name = full_name.split(".")
        schema.setdefault(db, {})[name] = {
            column: meta["type"] for column, meta in table["columns"].items()
        }
    return schema


def function_name(node: exp.Func) -> str:
    if isinstance(node, exp.Anonymous):
        return node.name.lower()
    return node.sql_name().lower()


def check_functions(tree: exp.Expression) -> None:
    for node in tree.find_all(exp.Func):
        name = function_name(node)
        if name in FORBIDDEN_FUNCTIONS or name.startswith(FORBIDDEN_PREFIXES):
            raise ValidationError(f"Function not allowed: {name}")


def check_tables(tree: exp.Expression, schema: Schema) -> None:
    cte_names = {cte.alias_or_name.lower() for cte in tree.find_all(exp.CTE)}
    for table in tree.find_all(exp.Table):
        if not isinstance(table.this, exp.Identifier):
            raise ValidationError("Table functions and file paths are not allowed in FROM")
        name, db = table.name.lower(), table.db.lower()
        if table.catalog:
            raise ValidationError(f"Database prefix not allowed: {table.sql(DIALECT)}")
        if not db:
            if name in cte_names:
                continue
            if any(char in name for char in "/\\.:"):
                raise ValidationError("File paths and URLs are not allowed as tables")
            raise ValidationError(f"Use schema-qualified table names (e.g. gold.{name})")
        if name not in schema.get(db, {}):
            raise ValidationError(f"Unknown table: {db}.{name}")


def check_columns(tree: exp.Expression, schema: Schema) -> None:
    try:
        qualify(
            tree.copy(),
            schema=schema,
            dialect=DIALECT,
            validate_qualify_columns=True,
        )
    except OptimizeError as error:
        raise ValidationError(f"Invalid column or reference: {error}") from error


def enforce_limit(tree: exp.Query, max_rows: int) -> exp.Query:
    limit = tree.args.get("limit")
    if limit is None:
        return tree.limit(max_rows)
    value = limit.expression
    if not (isinstance(value, exp.Literal) and value.is_int):
        raise ValidationError("LIMIT must be an integer literal")
    if int(value.this) > max_rows:
        return tree.limit(max_rows)
    return tree


def validate(sql: str, schema: Schema, max_rows: int = DEFAULT_MAX_ROWS) -> str:
    """Return a safe version of sql (with a LIMIT) or raise ValidationError."""
    try:
        statements = [s for s in sqlglot.parse(sql, read=DIALECT) if s is not None]
    except ParseError as error:
        raise ValidationError(f"SQL syntax error: {error}") from error
    if len(statements) != 1:
        raise ValidationError(f"Exactly one statement expected, got {len(statements)}")
    tree = statements[0]
    if not isinstance(tree, exp.Query):
        raise ValidationError(f"Only read queries are allowed, got {type(tree).__name__}")
    if tree.find(exp.DML, exp.DDL, exp.Command):
        raise ValidationError("Data modification is not allowed")
    check_functions(tree)
    check_tables(tree, schema)
    check_columns(tree, schema)
    return enforce_limit(tree, max_rows).sql(dialect=DIALECT)
