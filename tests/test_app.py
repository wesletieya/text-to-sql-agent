"""Tests for the API (with a scripted fake LLM) and the automatic chart choice."""

import json
from collections.abc import Iterator
from datetime import date
from decimal import Decimal
from pathlib import Path

import duckdb
import pytest
from fastapi.testclient import TestClient

import app.api as api
from agent.executor import connect
from agent.pipeline import Agent
from agent.schema_retriever import load_catalog
from app.charts import choose_chart
from tests.test_pipeline import BrokenLLM, FakeLLM, sql_answer

ROOT = Path(__file__).parent.parent
CATALOG = load_catalog(ROOT / "semantic/catalog.yaml")


@pytest.fixture
def con(lake_file: Path) -> Iterator[duckdb.DuckDBPyConnection]:
    connection = connect(lake_file)
    yield connection
    connection.close()


def client_for(agent: Agent) -> TestClient:
    return TestClient(api.create_app(agent))


def test_ask_returns_answer_sql_rows_and_metrics(con: duckdb.DuckDBPyConnection) -> None:
    llm = FakeLLM([sql_answer("SELECT sum(items_value) AS revenue FROM gold.fact_orders")])
    with client_for(Agent(llm, con, CATALOG)) as client:
        body = client.post("/ask", json={"question": "Total revenue?"}).json()
    assert body["status"] == "answered"
    assert body["answer"].startswith("revenue: ")
    assert isinstance(body["rows"][0][0], float)  # Decimal converted for JSON
    assert body["attempts"] == 1
    assert body["cost_usd"] is None  # the fake model has no price
    assert "LIMIT" in body["sql"]


def test_ask_rejects_empty_question(con: duckdb.DuckDBPyConnection) -> None:
    with client_for(Agent(FakeLLM([]), con, CATALOG)) as client:
        assert client.post("/ask", json={"question": ""}).status_code == 422


def test_llm_infrastructure_error_returns_503(con: duckdb.DuckDBPyConnection) -> None:
    with client_for(Agent(BrokenLLM([]), con, CATALOG)) as client:
        response = client.post("/ask", json={"question": "How many orders?"})
    assert response.status_code == 503
    assert "truncated" in response.json()["detail"]


def test_feedback_is_appended(
    con: duckdb.DuckDBPyConnection, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "feedback.jsonl"
    monkeypatch.setattr(api, "FEEDBACK_PATH", path)
    with client_for(Agent(FakeLLM([]), con, CATALOG)) as client:
        payload = {"question": "q", "sql": "SELECT 1", "rating": "down"}
        assert client.post("/feedback", json=payload).status_code == 200
    assert json.loads(path.read_text(encoding="utf-8"))["rating"] == "down"


def test_feedback_rating_is_validated(con: duckdb.DuckDBPyConnection) -> None:
    with client_for(Agent(FakeLLM([]), con, CATALOG)) as client:
        payload = {"question": "q", "rating": "meh"}
        assert client.post("/feedback", json=payload).status_code == 422


# --- automatic chart choice


def test_single_number_is_a_metric() -> None:
    assert choose_chart(["revenue"], [[Decimal("6108492.27")]]).kind == "metric"


def test_category_and_number_is_a_bar_chart() -> None:
    spec = choose_chart(["state", "orders"], [["SP", 40], ["RJ", 12]])
    assert (spec.kind, spec.x, spec.y) == ("bar", "state", "orders")


def test_dates_and_number_is_a_line_chart() -> None:
    spec = choose_chart(["month", "n"], [[date(2018, 1, 1), 7269], [date(2018, 2, 1), 6728]])
    assert spec.kind == "line"


def test_year_number_column_is_a_line_chart() -> None:
    assert choose_chart(["year", "n"], [[2016, 329], [2017, 45101]]).kind == "line"


@pytest.mark.parametrize(
    ("columns", "rows"),
    [
        (["a", "b", "c"], [["x", 1, 2], ["y", 3, 4]]),  # three columns
        (["state", "city"], [["SP", "sao paulo"], ["RJ", "rio"]]),  # no number
        (["id", "n"], [[f"id{i}", i] for i in range(50)]),  # too many bars
        (["state"], [["SP"]]),  # single text value
    ],
)
def test_other_shapes_get_no_chart(columns: list[str], rows: list[list]) -> None:
    assert choose_chart(columns, rows) is None


# --- Streamlit page, rendered headless with a fake API


class FakeResponse:
    status_code = 200

    def __init__(self, body: dict) -> None:
        self.body = body

    def json(self) -> dict:
        return self.body


def test_ui_shows_answer_sql_chart_and_table(monkeypatch: pytest.MonkeyPatch) -> None:
    from streamlit.testing.v1 import AppTest

    body = {
        "status": "answered",
        "answer": "2 rows.",
        "sql": "SELECT state, count(*) AS n FROM gold.dim_customer GROUP BY state LIMIT 1000",
        "columns": ["state", "n"],
        "rows": [["SP", 40296], ["RJ", 12381]],
        "truncated": False,
        "attempts": 1,
        "latency_ms": 1200.0,
        "input_tokens": 100,
        "output_tokens": 10,
        "cost_usd": 0.0,
        "model": "fake",
    }
    monkeypatch.setattr("requests.post", lambda *args, **kwargs: FakeResponse(body))

    page = AppTest.from_file(str(ROOT / "app/ui.py"), default_timeout=30).run()
    page.chat_input[0].set_value("Customers per state?").run()

    assert not page.exception
    assert "Customers per state?" in page.markdown[0].value or any(
        "Customers per state?" in m.value for m in page.markdown
    )
    assert "SELECT state" in page.code[0].value
    assert len(page.dataframe) == 1
    assert page.get("vega_lite_chart")  # the automatic bar chart
