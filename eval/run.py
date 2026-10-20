"""Run the agent on eval/dataset.jsonl and write one JSON line per (run, question).

uv run python -m eval.run --model qwen2.5-coder:7b --runs 3
"""

import argparse
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from agent.executor import connect, execute
from agent.llm import LLMError, get_llm
from agent.pipeline import Agent
from agent.schema_retriever import load_catalog, load_fewshot
from eval.check_dataset import Question, gold_problems, load_dataset, static_problems
from eval.metrics import is_correct, results_match
from eval.report import print_summary

RESULTS_DIR = Path("eval/results")
PRICING_PATH = Path("eval/pricing.yaml")
LAKE_PATH = Path(os.environ.get("LAKE_PATH", "data/lake.duckdb"))


def load_pricing(path: Path = PRICING_PATH) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))["models"]


def cost_usd(
    pricing: dict[str, Any], model: str, input_tokens: int, output_tokens: int
) -> float | None:
    """Cost from eval/pricing.yaml; None when the model has no recorded price."""
    price = pricing.get(model)
    if price is None:
        return None
    total = input_tokens * price["input_per_mtok"] + output_tokens * price["output_per_mtok"]
    return round(total / 1_000_000, 6)


def results_path(model: str) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return RESULTS_DIR / f"{stamp}_{re.sub(r'[^A-Za-z0-9.-]+', '-', model)}.jsonl"


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate a model on the dataset.")
    parser.add_argument("--model", required=True)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--limit", type=int, help="only the first N questions")
    parser.add_argument("--ids", help="comma-separated question ids")
    args = parser.parse_args()

    questions = load_dataset()
    catalog = load_catalog()
    pricing = load_pricing()
    if args.model not in pricing:
        print(f"Warning: {args.model} is not in {PRICING_PATH}; cost will be null.")

    with connect(LAKE_PATH) as con:
        problems = static_problems(questions, load_fewshot()) + gold_problems(
            questions, catalog, con
        )
        if problems:
            raise SystemExit("Fix the dataset first:\n" + "\n".join(problems))
        if args.ids:
            wanted = set(args.ids.split(","))
            questions = [q for q in questions if q.id in wanted]
        if args.limit:
            questions = questions[: args.limit]

        gold = {q.id: execute(con, q.gold_sql).rows for q in questions if q.gold_sql}
        agent = Agent(get_llm(args.model), con, catalog)
        out = results_path(args.model)
        out.parent.mkdir(parents=True, exist_ok=True)
        print(f"{len(questions)} questions x {args.runs} runs -> {out}")

        try:
            run_all(agent, questions, gold, pricing, args, out)
        except LLMError as error:
            # Infrastructure problem (truncated prompt, missing key...): not the model's fault,
            # so the partial results are discarded instead of being scored as failures.
            out.unlink(missing_ok=True)
            raise SystemExit(f"Evaluation aborted: {error}") from error

    print_summary([out])


def run_all(
    agent: Agent,
    questions: list[Question],
    gold: dict[str, list[list[Any]]],
    pricing: dict[str, Any],
    args: argparse.Namespace,
    out: Path,
) -> None:
    with out.open("w", encoding="utf-8") as f:
        for run in range(1, args.runs + 1):
            for i, q in enumerate(questions, 1):
                result = agent.answer(q.question)
                matched = q.gold_sql is not None and results_match(
                    gold[q.id], result.rows, q.order_matters
                )
                correct = is_correct(q.expected, result.status, matched)
                record = {
                    "timestamp": datetime.now().isoformat(timespec="seconds"),
                    "model": args.model,
                    "run": run,
                    "id": q.id,
                    "category": q.category,
                    "difficulty": q.difficulty,
                    "expected": q.expected,
                    "status": result.status,
                    "correct": correct,
                    "sql": result.sql,
                    "attempts": len(result.attempts),
                    "errors": [a.error for a in result.attempts if a.error],
                    "latency_ms": result.latency_ms,
                    "input_tokens": result.input_tokens,
                    "output_tokens": result.output_tokens,
                    "cost_usd": cost_usd(
                        pricing, args.model, result.input_tokens, result.output_tokens
                    ),
                }
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
                f.flush()
                mark = "OK " if correct else "KO "
                print(f"run {run} [{i}/{len(questions)}] {mark} {q.id} {q.question[:60]}")


if __name__ == "__main__":
    main()
