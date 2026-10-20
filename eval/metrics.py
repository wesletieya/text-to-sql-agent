"""Compare execution results, never SQL text.

Two results match when they contain the same rows, with these tolerances:
- column order and column names are ignored, and extra predicted columns are allowed
  (e.g. returning the count next to the requested name);
- row order is ignored unless the question asks for an ordering (order_matters);
- numbers are compared rounded to 2 decimals, so 12.063588 matches 12.06;
- dates and midnight timestamps are equivalent; NULL only matches NULL.
"""

import itertools
from collections import Counter
from datetime import date, datetime
from decimal import Decimal
from typing import Any

ROUND_DIGITS = 2
MAX_MAPPINGS = 10_000

Row = tuple[Any, ...]


def normalize_value(value: Any) -> Any:
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int | float | Decimal):
        rounded = round(float(value), ROUND_DIGITS)
        return 0.0 if rounded == 0 else rounded
    if isinstance(value, datetime):
        if value.time() == datetime.min.time():
            return value.date().isoformat()
        return value.isoformat(sep=" ")
    if isinstance(value, date):
        return value.isoformat()
    return str(value).strip()


def sort_key(row: Row) -> tuple[Any, ...]:
    return tuple((value is None, type(value).__name__, str(value)) for value in row)


def normalize_rows(rows: list[list[Any]] | list[Row]) -> list[Row]:
    return [tuple(normalize_value(value) for value in row) for row in rows]


def results_match(gold_rows: list[Row], pred_rows: list[Row], order_matters: bool = False) -> bool:
    """True if pred contains exactly the gold rows (see module docstring for tolerances)."""
    gold = normalize_rows(gold_rows)
    pred = normalize_rows(pred_rows)
    if len(gold) != len(pred):
        return False
    if not gold:
        return True
    gold_width, pred_width = len(gold[0]), len(pred[0])
    if pred_width < gold_width:
        return False

    # Candidate predicted columns for each gold column: same multiset of values.
    def column(rows: list[Row], index: int) -> Counter:
        return Counter(row[index] for row in rows)

    candidates = [
        [k for k in range(pred_width) if column(pred, k) == column(gold, j)]
        for j in range(gold_width)
    ]
    if any(not options for options in candidates):
        return False

    expected = gold if order_matters else sorted(gold, key=sort_key)
    for mapping in itertools.islice(itertools.product(*candidates), MAX_MAPPINGS):
        if len(set(mapping)) != len(mapping):
            continue
        projected = [tuple(row[k] for k in mapping) for row in pred]
        if not order_matters:
            projected = sorted(projected, key=sort_key)
        if projected == expected:
            return True
    return False


def is_correct(expected: str, status: str, matched: bool) -> bool:
    """A question is correct if the agent behaved as expected (answered right, or refused)."""
    if expected == "answer":
        return status == "answered" and matched
    return status == expected
