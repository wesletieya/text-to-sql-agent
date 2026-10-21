"""Tests for the evaluation: result matching, dataset integrity, costs and report."""

import os
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import duckdb
import pytest

from agent.pricing import cost_usd, load_pricing
from agent.schema_retriever import load_catalog, load_fewshot
from eval.check_dataset import gold_problems, load_dataset, static_problems
from eval.metrics import is_correct, results_match
from eval.report import pareto_front, render

ROOT = Path(__file__).parent.parent
DATASET = load_dataset(ROOT / "eval/dataset.jsonl")
LAKE_PATH = Path(os.environ.get("LAKE_PATH", ROOT / "data/lake.duckdb"))

# --- results_match


def test_identical_results_match() -> None:
    assert results_match([("SP", 10), ("RJ", 5)], [("SP", 10), ("RJ", 5)])


def test_row_order_is_ignored_by_default() -> None:
    assert results_match([("SP", 10), ("RJ", 5)], [("RJ", 5), ("SP", 10)])


def test_row_order_counts_when_required() -> None:
    assert not results_match([(2016, 1), (2017, 2)], [(2017, 2), (2016, 1)], order_matters=True)


def test_column_order_is_ignored() -> None:
    assert results_match([("SP", 10), ("RJ", 5)], [(10, "SP"), (5, "RJ")])


def test_columns_must_stay_aligned_within_rows() -> None:
    assert not results_match([("SP", 10), ("RJ", 5)], [("SP", 5), ("RJ", 10)])


def test_extra_predicted_columns_are_allowed() -> None:
    assert results_match([("SP",)], [("SP", 40296)])


def test_missing_column_does_not_match() -> None:
    assert not results_match([("SP", 40296)], [("SP",)])


def test_numbers_are_rounded_to_two_decimals() -> None:
    assert results_match([(12.06,)], [(12.063588,)])
    assert results_match([(Decimal("6108492.27"),)], [(6108492.2700001,)])
    assert not results_match([(12.06,)], [(12.1,)])


def test_fraction_and_percentage_differ() -> None:
    assert not results_match([(0.0677,)], [(6.77,)])


def test_dates_and_midnight_timestamps_match() -> None:
    assert results_match([(date(2016, 9, 4),)], [(datetime(2016, 9, 4),)])


def test_null_only_matches_null() -> None:
    assert results_match([(None,)], [(None,)])
    assert not results_match([(None,)], [(0,)])


def test_different_row_counts_do_not_match() -> None:
    assert not results_match([("SP",)], [("SP",), ("RJ",)])


def test_refusal_is_correct_only_when_expected() -> None:
    assert is_correct("out_of_scope", "out_of_scope", matched=False)
    assert not is_correct("answer", "out_of_scope", matched=False)
    assert not is_correct("answer", "answered", matched=False)
    assert is_correct("answer", "answered", matched=True)


# --- dataset integrity


def test_dataset_has_enough_questions() -> None:
    assert 80 <= len(DATASET) <= 150


def test_dataset_has_no_static_problem() -> None:
    assert static_problems(DATASET, load_fewshot(ROOT / "semantic/fewshot.yaml")) == []


def test_fewshot_overlap_is_detected() -> None:
    fewshot = [{"question": DATASET[0].question, "sql": "SELECT 1"}]
    assert static_problems(DATASET[:1], fewshot)


@pytest.mark.skipif(not LAKE_PATH.exists(), reason="run `make data` first")
def test_every_gold_query_is_valid_and_returns_rows() -> None:
    catalog = load_catalog(ROOT / "semantic/catalog.yaml")
    with duckdb.connect(str(LAKE_PATH), read_only=True) as con:
        assert gold_problems(DATASET, catalog, con) == []


# --- cost and report


def test_cost_uses_pricing_file() -> None:
    pricing = load_pricing(ROOT / "eval/pricing.yaml")
    assert (
        cost_usd(pricing, "claude-opus-5-5", 1_000_000, 0)
        == pricing["claude-opus-5-5"]["input_per_mtok"]
    )
    assert cost_usd(pricing, "qwen2.5-coder:7b", 5000, 100) == 0


def test_unknown_model_cost_is_null_not_guessed() -> None:
    assert cost_usd({}, "mystery-model", 1000, 1000) is None


def record(model: str, run: int, correct: bool, cost: float | None = 0.0) -> dict:
    return {
        "model": model,
        "run": run,
        "id": "q001",
        "category": "aggregation",
        "difficulty": "easy",
        "expected": "answer",
        "status": "answered",
        "correct": correct,
        "attempts": 1,
        "latency_ms": 1000,
        "input_tokens": 100,
        "output_tokens": 10,
        "cost_usd": cost,
    }


def test_pareto_front_drops_dominated_models() -> None:
    summaries = {
        "cheap_good": {"accuracy": 0.8, "cost_per_question": 0.0},
        "costly_worse": {"accuracy": 0.7, "cost_per_question": 0.01},
        "costly_better": {"accuracy": 0.9, "cost_per_question": 0.01},
    }
    assert sorted(pareto_front(summaries)) == ["cheap_good", "costly_better"]


def test_report_renders_accuracy_per_model() -> None:
    report = render([record("a", 1, True), record("a", 2, False), record("b", 1, True)])
    assert "| a | 2 | 50.0%" in report
    assert "| b | 1 | 100.0%" in report
