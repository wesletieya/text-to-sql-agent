"""Check eval/dataset.jsonl: well-formed, disjoint from the few-shot examples, gold SQL valid.

uv run python -m eval.check_dataset
"""

import json
import os
import re
from pathlib import Path
from typing import Any, Literal

import duckdb
from pydantic import BaseModel

from agent.executor import connect
from agent.schema_retriever import load_catalog, load_fewshot
from agent.validator import ValidationError, schema_from_catalog, validate

DATASET_PATH = Path("eval/dataset.jsonl")
LAKE_PATH = Path(os.environ.get("LAKE_PATH", "data/lake.duckdb"))


class Question(BaseModel):
    id: str
    category: str
    difficulty: Literal["easy", "medium", "hard"]
    question: str
    expected: Literal["answer", "out_of_scope", "needs_clarification"]
    gold_sql: str | None
    order_matters: bool = False


def load_dataset(path: Path = DATASET_PATH) -> list[Question]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [Question.model_validate_json(line) for line in lines if line.strip()]


def normalize_text(text: str) -> str:
    return re.sub(r"\W+", " ", text.lower()).strip()


def static_problems(questions: list[Question], fewshot: list[dict[str, str]]) -> list[str]:
    """Problems that can be found without the database."""
    problems = []
    ids = [q.id for q in questions]
    problems += [f"duplicate id {i}" for i in {i for i in ids if ids.count(i) > 1}]
    fewshot_questions = {normalize_text(e["question"]) for e in fewshot}
    fewshot_sql = {normalize_text(e["sql"]) for e in fewshot}
    for q in questions:
        if normalize_text(q.question) in fewshot_questions:
            problems.append(f"{q.id}: question also appears in fewshot.yaml")
        if q.gold_sql and normalize_text(q.gold_sql) in fewshot_sql:
            problems.append(f"{q.id}: gold_sql also appears in fewshot.yaml")
        if (q.expected == "answer") != (q.gold_sql is not None):
            problems.append(f"{q.id}: gold_sql must be set if and only if expected is 'answer'")
    return problems


def gold_problems(
    questions: list[Question], catalog: dict[str, Any], con: duckdb.DuckDBPyConnection
) -> list[str]:
    """Every gold query must pass the validator (or the agent could never match it) and run."""
    schema = schema_from_catalog(catalog)
    problems = []
    for q in questions:
        if not q.gold_sql:
            continue
        try:
            validate(q.gold_sql, schema)
            if not con.execute(q.gold_sql).fetchall():
                problems.append(f"{q.id}: gold_sql returns no rows")
        except (ValidationError, duckdb.Error) as error:
            problems.append(f"{q.id}: {error}")
    return problems


def main() -> None:
    questions = load_dataset()
    problems = static_problems(questions, load_fewshot())
    with connect(LAKE_PATH) as con:
        problems += gold_problems(questions, load_catalog(), con)
    categories: dict[str, int] = {}
    for q in questions:
        categories[q.category] = categories.get(q.category, 0) + 1
    print(f"{len(questions)} questions: {json.dumps(categories)}")
    if problems:
        raise SystemExit("\n".join(problems))
    print("Dataset OK")


if __name__ == "__main__":
    main()
