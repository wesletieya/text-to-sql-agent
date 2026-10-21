"""HTTP API around the agent.

POST /ask       {"question": "..."} -> answer, SQL, rows, latency, cost, attempts
POST /feedback  {"question", "sql", "rating": "up" | "down"} -> appended to logs/feedback.jsonl
GET  /health

uv run uvicorn app.api:app
"""

import json
import logging
import os
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from agent.executor import connect
from agent.llm import LLMError, get_llm
from agent.pipeline import Agent, PipelineResult
from agent.pricing import cost_usd, load_pricing
from agent.schema_retriever import load_catalog

LAKE_PATH = Path(os.environ.get("LAKE_PATH", "data/lake.duckdb"))
FEEDBACK_PATH = Path(os.environ.get("FEEDBACK_PATH", "logs/feedback.jsonl"))
DEFAULT_MODEL = os.environ.get("MODEL", "qwen2.5-coder:7b")

logging.basicConfig(level=logging.WARNING, format="%(message)s")
logging.getLogger("agent").setLevel(logging.INFO)


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500)


class AskResponse(BaseModel):
    status: str
    answer: str
    sql: str | None
    columns: list[str]
    rows: list[list[Any]]
    truncated: bool
    attempts: int
    latency_ms: float
    input_tokens: int
    output_tokens: int
    cost_usd: float | None
    model: str


class Feedback(BaseModel):
    question: str
    sql: str | None = None
    rating: Literal["up", "down"]
    comment: str | None = Field(default=None, max_length=1000)


def json_value(value: Any) -> Any:
    """Make DuckDB values JSON-friendly: Decimal -> float, dates -> ISO strings."""
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    return value


def summarize(result: PipelineResult) -> str:
    """A short text answer, without a second LLM call."""
    if result.status != "answered":
        return result.message or "No answer."
    if not result.rows:
        return "The query returned no rows."
    if len(result.rows) == 1 and len(result.columns) == 1:
        return f"{result.columns[0]}: {json_value(result.rows[0][0])}"
    more = " (truncated)" if result.truncated else ""
    return f"{len(result.rows)} rows{more}."


def to_response(result: PipelineResult, pricing: dict[str, Any]) -> AskResponse:
    return AskResponse(
        status=result.status,
        answer=summarize(result),
        sql=result.sql,
        columns=result.columns,
        rows=[[json_value(v) for v in row] for row in result.rows],
        truncated=result.truncated,
        attempts=len(result.attempts),
        latency_ms=result.latency_ms,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        cost_usd=cost_usd(pricing, result.model, result.input_tokens, result.output_tokens),
        model=result.model,
    )


def create_app(agent: Agent | None = None) -> FastAPI:
    """Build the app. Tests pass their own agent; otherwise it is built from the environment."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if agent is not None:
            app.state.agent = agent
            yield
            return
        with connect(LAKE_PATH) as con:
            app.state.agent = Agent(get_llm(DEFAULT_MODEL), con, load_catalog())
            yield

    app = FastAPI(title="Text-to-SQL Lakehouse Agent", lifespan=lifespan)
    pricing = load_pricing()
    # One DuckDB connection is shared: requests are answered one at a time.
    lock = threading.Lock()

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "model": app.state.agent.llm.model}

    @app.post("/ask")
    def ask(request: AskRequest) -> AskResponse:
        with lock:
            try:
                result = app.state.agent.answer(request.question)
            except LLMError as error:
                raise HTTPException(status_code=503, detail=str(error)) from error
        return to_response(result, pricing)

    @app.post("/feedback")
    def feedback(item: Feedback) -> dict[str, str]:
        FEEDBACK_PATH.parent.mkdir(parents=True, exist_ok=True)
        record = {"timestamp": datetime.now().isoformat(timespec="seconds"), **item.model_dump()}
        with FEEDBACK_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        return {"status": "saved"}

    return app


app = create_app()
