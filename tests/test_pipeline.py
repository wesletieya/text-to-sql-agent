"""Pipeline tests with a scripted fake LLM: no network, no Ollama needed."""

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import duckdb
import pytest

from agent.executor import connect
from agent.llm import LLMResponse
from agent.pipeline import Agent
from agent.schema_retriever import load_catalog

ROOT = Path(__file__).parent.parent
CATALOG = load_catalog(ROOT / "semantic/catalog.yaml")


class FakeLLM:
    """Returns the scripted answers in order and records every prompt it receives."""

    model = "fake"

    def __init__(self, answers: list[dict[str, Any] | str]) -> None:
        self.answers = list(answers)
        self.prompts: list[str] = []

    def complete(self, system: str, user: str, schema: dict[str, Any]) -> LLMResponse:
        self.prompts.append(user)
        answer = self.answers.pop(0)
        text = answer if isinstance(answer, str) else json.dumps(answer)
        return LLMResponse(
            text=text, model=self.model, input_tokens=100, output_tokens=10, latency_ms=1
        )


def sql_answer(sql: str) -> dict[str, Any]:
    return {
        "reasoning": "test",
        "out_of_scope": False,
        "needs_clarification": False,
        "clarification_question": None,
        "sql": sql,
    }


VALID = sql_answer("SELECT count(*) AS orders FROM gold.fact_orders")
INVALID_COLUMN = sql_answer("SELECT count(vip) FROM gold.fact_orders")


@pytest.fixture
def con(lake_file: Path) -> Iterator[duckdb.DuckDBPyConnection]:
    connection = connect(lake_file)
    yield connection
    connection.close()


def run(con: duckdb.DuckDBPyConnection, answers: list[dict[str, Any] | str]) -> tuple:
    llm = FakeLLM(answers)
    result = Agent(llm, con, CATALOG).answer("How many orders?")
    return result, llm


def test_answers_on_first_attempt(con: duckdb.DuckDBPyConnection) -> None:
    result, _ = run(con, [VALID])
    assert result.status == "answered"
    assert result.columns == ["orders"]
    assert result.rows[0][0] > 0
    assert len(result.attempts) == 1
    assert "LIMIT" in result.sql


def test_self_corrects_with_the_validator_error(con: duckdb.DuckDBPyConnection) -> None:
    result, llm = run(con, [INVALID_COLUMN, VALID])
    assert result.status == "answered"
    assert len(result.attempts) == 2
    assert "vip" in llm.prompts[1] and "could not be resolved" in llm.prompts[1]


def test_gives_up_after_two_corrections(con: duckdb.DuckDBPyConnection) -> None:
    result, _ = run(con, [INVALID_COLUMN] * 3)
    assert result.status == "failed"
    assert len(result.attempts) == 3
    assert result.rows == []


def test_malformed_json_counts_as_an_attempt(con: duckdb.DuckDBPyConnection) -> None:
    result, _ = run(con, ["this is not json", VALID])
    assert result.status == "answered"
    assert result.attempts[0].error


def test_dangerous_sql_from_the_llm_is_never_executed(con: duckdb.DuckDBPyConnection) -> None:
    attack = sql_answer("DROP TABLE gold.fact_orders")
    result, _ = run(con, [attack] * 3)
    assert result.status == "failed"
    assert all("Only read queries" in a.error for a in result.attempts)
    assert con.execute("SELECT count(*) FROM gold.fact_orders").fetchone()[0] > 0


def test_out_of_scope_question_runs_no_sql(con: duckdb.DuckDBPyConnection) -> None:
    answer = {**sql_answer(""), "out_of_scope": True, "sql": None, "reasoning": "Weather data"}
    result, _ = run(con, [answer])
    assert result.status == "out_of_scope"
    assert result.sql is None


def test_ambiguous_question_asks_for_clarification(con: duckdb.DuckDBPyConnection) -> None:
    answer = {
        **sql_answer(""),
        "needs_clarification": True,
        "clarification_question": "Best by revenue or by number of orders?",
        "sql": None,
    }
    result, _ = run(con, [answer])
    assert result.status == "needs_clarification"
    assert result.message == "Best by revenue or by number of orders?"


def test_tokens_are_summed_over_attempts(con: duckdb.DuckDBPyConnection) -> None:
    result, _ = run(con, [INVALID_COLUMN, VALID])
    assert result.input_tokens == 200
    assert result.output_tokens == 20
