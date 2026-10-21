"""Choose an automatic chart from the shape of a query result (pure logic, no Streamlit).

- one value                         -> a metric tile, not a chart
- a time column + one number        -> a line chart (change over time)
- a text column + one number        -> a horizontal bar chart, sorted (comparison)
- anything else                     -> no chart, the table is enough
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel

MAX_BARS = 30
TIME_COLUMN_NAMES = {"year", "month", "quarter", "date", "day", "week"}


class ChartSpec(BaseModel):
    kind: Literal["metric", "line", "bar"]
    x: str | None = None
    y: str | None = None


def is_number(value: Any) -> bool:
    return isinstance(value, int | float | Decimal) and not isinstance(value, bool)


def is_time_column(name: str, values: list[Any]) -> bool:
    if all(isinstance(v, date | datetime) for v in values if v is not None):
        return True
    return name.lower() in TIME_COLUMN_NAMES and all(is_number(v) for v in values)


def choose_chart(columns: list[str], rows: list[list[Any]]) -> ChartSpec | None:
    if len(rows) == 1 and len(columns) == 1 and is_number(rows[0][0]):
        return ChartSpec(kind="metric", y=columns[0])
    if len(columns) != 2 or len(rows) < 2:
        return None

    first = [row[0] for row in rows]
    second = [row[1] for row in rows]
    if not all(is_number(v) for v in second if v is not None):
        return None
    if is_time_column(columns[0], first):
        return ChartSpec(kind="line", x=columns[0], y=columns[1])
    if all(isinstance(v, str) for v in first) and len(rows) <= MAX_BARS:
        return ChartSpec(kind="bar", x=columns[0], y=columns[1])
    return None
