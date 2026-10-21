"""Streamlit interface: ask a question, see the answer, the SQL, the table and a chart.

uv run streamlit run app/ui.py   (the API must be running: uv run uvicorn app.api:app)
"""

import os
import sys
from pathlib import Path
from typing import Any

import altair as alt
import pandas as pd
import requests
import streamlit as st

# Streamlit runs this file as a script: make the project root importable.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.charts import ChartSpec, choose_chart  # noqa: E402

API_URL = os.environ.get("API_URL", "http://localhost:8000")
SERIES_COLOR = "#2a78d6"  # single series: one color, the title names it (no legend)
TIMEOUT_S = 180

EXAMPLES = [
    "What was the revenue in 2017?",
    "Which 5 product categories have the most items sold?",
    "How many orders were placed each month in 2018?",
    "What percentage of delivered orders arrived late?",
]

STATUS_LABELS = {
    "answered": "✅ Answered",
    "needs_clarification": "❓ Needs clarification",
    "out_of_scope": "🚫 Out of scope",
    "failed": "⚠️ No valid query found",
}


def ask(question: str) -> dict[str, Any]:
    response = requests.post(f"{API_URL}/ask", json={"question": question}, timeout=TIMEOUT_S)
    if response.status_code != 200:
        detail = response.json().get("detail", response.text)
        raise RuntimeError(f"API error {response.status_code}: {detail}")
    return response.json()


def send_feedback(question: str, sql: str | None, rating: str) -> None:
    payload = {"question": question, "sql": sql, "rating": rating}
    requests.post(f"{API_URL}/feedback", json=payload, timeout=10)


def render_chart(spec: ChartSpec, df: pd.DataFrame) -> None:
    if spec.kind == "metric":
        value = df.iloc[0, 0]
        st.metric(spec.y, f"{value:,.2f}" if isinstance(value, float) else f"{value:,}")
        return
    if spec.kind == "line":
        chart = (
            alt.Chart(df)
            .mark_line(strokeWidth=2, color=SERIES_COLOR, point=alt.OverlayMarkDef(size=60))
            .encode(x=alt.X(spec.x), y=alt.Y(spec.y), tooltip=[spec.x, spec.y])
        )
    else:
        chart = (
            alt.Chart(df)
            .mark_bar(color=SERIES_COLOR, cornerRadiusEnd=4)
            .encode(
                y=alt.Y(spec.x, sort="-x", title=None),
                x=alt.X(spec.y),
                tooltip=[spec.x, alt.Tooltip(spec.y, format=",.2f")],
            )
        )
    st.altair_chart(chart.properties(title=f"{spec.y} by {spec.x}"), width="stretch")


def render_result(index: int, item: dict[str, Any]) -> None:
    question, result = item["question"], item["result"]
    st.markdown(f"### {question}")
    st.markdown(f"**{STATUS_LABELS.get(result['status'], result['status'])}** · {result['answer']}")

    if result["sql"]:
        with st.expander("SQL"):
            st.code(result["sql"], language="sql")
        df = pd.DataFrame(result["rows"], columns=result["columns"])
        spec = choose_chart(result["columns"], result["rows"])
        if spec:
            render_chart(spec, df)
        st.dataframe(df, width="stretch", hide_index=True)

    cost = "n/a" if result["cost_usd"] is None else f"${result['cost_usd']:.5f}"
    st.caption(
        f"{result['model']} · {result['latency_ms'] / 1000:.1f} s · "
        f"{result['attempts']} attempt(s) · {result['input_tokens'] + result['output_tokens']:,} "
        f"tokens · {cost}"
    )

    if item.get("rated"):
        st.caption("Thanks for your feedback.")
    else:
        up, down, _ = st.columns([1, 1, 10])
        for column, rating, label in [(up, "up", "👍"), (down, "down", "👎")]:
            if column.button(label, key=f"{rating}-{index}"):
                send_feedback(question, result["sql"], rating)
                item["rated"] = True
                st.rerun()
    st.divider()


def main() -> None:
    st.set_page_config(page_title="Text-to-SQL Lakehouse", page_icon="🗄️", layout="wide")
    st.title("Text-to-SQL Lakehouse")
    st.caption(
        "Ask a question about the Olist e-commerce data (2016-2018) or the TPC-H benchmark. "
        "The SQL is validated and runs read-only."
    )
    st.session_state.setdefault("history", [])

    cols = st.columns(len(EXAMPLES))
    clicked = next((q for col, q in zip(cols, EXAMPLES, strict=True) if col.button(q)), None)
    question = st.chat_input("Ask a question in English...") or clicked

    if question:
        with st.spinner("Generating and validating SQL..."):
            try:
                result = ask(question)
            except (requests.RequestException, RuntimeError) as error:
                st.error(f"{error}")
                result = None
        if result:
            st.session_state.history.insert(0, {"question": question, "result": result})

    for index, item in enumerate(st.session_state.history):
        render_result(index, item)


main()
