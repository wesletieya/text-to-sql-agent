"""Question -> SQL -> validated -> executed, with up to 2 self-corrections.

CLI: uv run python -m agent.pipeline "How many orders were delivered late?" --model qwen2.5-coder:7b
"""

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Literal

import duckdb
from pydantic import BaseModel

from agent.executor import QueryTimeoutError, connect, execute
from agent.generator import GenerationError, generate
from agent.llm import LLM, LLMError, get_llm
from agent.schema_retriever import load_catalog, load_fewshot, render_fewshot, render_schema
from agent.validator import ValidationError, schema_from_catalog, validate

MAX_CORRECTIONS = 2
MAX_ERROR_CHARS = 300
LAKE_PATH = Path(os.environ.get("LAKE_PATH", "data/lake.duckdb"))

logger = logging.getLogger("agent")

Status = Literal["answered", "needs_clarification", "out_of_scope", "failed"]


class Attempt(BaseModel):
    sql: str | None = None
    error: str | None = None


class PipelineResult(BaseModel):
    question: str
    status: Status
    message: str | None = None
    sql: str | None = None
    columns: list[str] = []
    rows: list[list[Any]] = []
    truncated: bool = False
    attempts: list[Attempt] = []
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: float = 0.0


class Agent:
    """Holds what is loaded once (catalog, prompt parts, connection) and answers questions."""

    def __init__(self, llm: LLM, con: duckdb.DuckDBPyConnection, catalog: dict[str, Any]) -> None:
        self.llm = llm
        self.con = con
        self.schema = schema_from_catalog(catalog)
        self.schema_text = render_schema(catalog)
        self.fewshot_text = render_fewshot(load_fewshot())

    def answer(self, question: str) -> PipelineResult:
        start = time.perf_counter()
        result = PipelineResult(question=question, status="failed", model=self.llm.model)
        feedback: list[str] = []

        for _ in range(1 + MAX_CORRECTIONS):
            attempt = Attempt()
            result.attempts.append(attempt)
            try:
                generation, response = generate(
                    self.llm, question, self.schema_text, self.fewshot_text, feedback
                )
            except GenerationError as error:
                self._count_tokens(result, error.response)
                attempt.error = str(error)[:MAX_ERROR_CHARS]
                feedback.append(attempt.error)
                continue
            except LLMError as error:
                attempt.error = str(error)
                result.message = attempt.error
                break
            self._count_tokens(result, response)

            if generation.out_of_scope:
                result.status = "out_of_scope"
                result.message = generation.reasoning
                break
            if generation.needs_clarification:
                result.status = "needs_clarification"
                result.message = generation.clarification_question or generation.reasoning
                break

            attempt.sql = generation.sql
            try:
                safe_sql = validate(generation.sql or "", self.schema)
                rows = execute(self.con, safe_sql)
            except (ValidationError, QueryTimeoutError, duckdb.Error) as error:
                # Only the error message goes back to the LLM, never data rows.
                attempt.error = f"{type(error).__name__}: {error}"[:MAX_ERROR_CHARS]
                feedback.append(f"SQL: {generation.sql}\nError: {attempt.error}")
                continue

            result.status = "answered"
            result.sql = safe_sql
            result.columns = rows.columns
            result.rows = rows.rows
            result.truncated = rows.truncated
            break
        else:
            result.message = f"No valid query after {len(result.attempts)} attempts"

        result.latency_ms = round((time.perf_counter() - start) * 1000, 1)
        log_result(result)
        return result

    @staticmethod
    def _count_tokens(result: PipelineResult, response: Any) -> None:
        result.input_tokens += response.input_tokens
        result.output_tokens += response.output_tokens


def log_result(result: PipelineResult) -> None:
    """One structured JSON log line per question (rows are not logged)."""
    logger.info(
        json.dumps(
            {
                "question": result.question,
                "status": result.status,
                "model": result.model,
                "sql": result.sql,
                "attempts": len(result.attempts),
                "errors": [a.error for a in result.attempts if a.error],
                "latency_ms": result.latency_ms,
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
            },
            ensure_ascii=False,
        )
    )


def print_result(result: PipelineResult) -> None:
    import pandas as pd

    print(f"Status: {result.status} ({len(result.attempts)} attempt(s), {result.latency_ms} ms)")
    if result.message:
        print(result.message)
    if result.sql:
        print(f"\nSQL:\n{result.sql}\n")
        print(pd.DataFrame(result.rows, columns=result.columns).head(20).to_string(index=False))
        if result.truncated:
            print("(result truncated)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Ask a question to the lakehouse.")
    parser.add_argument("question")
    parser.add_argument("--model", default=os.environ.get("MODEL", "qwen2.5-coder:7b"))
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING, format="%(message)s", stream=sys.stderr)
    logger.setLevel(logging.INFO)

    with connect(LAKE_PATH) as con:
        agent = Agent(get_llm(args.model), con, load_catalog())
        print_result(agent.answer(args.question))


if __name__ == "__main__":
    main()
