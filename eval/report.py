"""Summarize eval results: accuracy per model (mean and spread over runs), by category,
latency, tokens, cost, and which models are on the accuracy/cost Pareto front.

uv run python -m eval.report                 # every file in eval/results/
uv run python -m eval.report results.jsonl   # specific files
"""

import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

RESULTS_DIR = Path("eval/results")
REPORT_PATH = RESULTS_DIR / "report.md"


def load_records(paths: list[Path]) -> list[dict[str, Any]]:
    records = []
    for path in paths:
        lines = path.read_text(encoding="utf-8").splitlines()
        records += [json.loads(line) for line in lines if line.strip()]
    return records


def rate(records: list[dict[str, Any]]) -> float:
    return sum(r["correct"] for r in records) / len(records) if records else 0.0


def percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(q * len(ordered)))]


def summarize_model(records: list[dict[str, Any]]) -> dict[str, Any]:
    by_run: dict[int, list] = defaultdict(list)
    for r in records:
        by_run[r["run"]].append(r)
    run_accuracies = [rate(rs) for rs in by_run.values()]
    answerable = [r for r in records if r["expected"] == "answer"]
    refusals = [r for r in records if r["expected"] != "answer"]
    costs = [r["cost_usd"] for r in records]
    known_cost = None not in costs
    latencies = [r["latency_ms"] for r in records]
    return {
        "runs": len(by_run),
        "questions": len(records) // max(1, len(by_run)),
        "accuracy": statistics.mean(run_accuracies),
        "accuracy_std": statistics.pstdev(run_accuracies),
        "execution_accuracy": rate(answerable),
        "valid_sql_rate": (
            sum(r["status"] == "answered" for r in answerable) / len(answerable)
            if answerable
            else 0.0
        ),
        "refusal_accuracy": rate(refusals),
        "false_refusals": sum(
            r["status"] in ("out_of_scope", "needs_clarification") for r in answerable
        ),
        "avg_attempts": statistics.mean(r["attempts"] for r in records),
        "latency_avg_s": statistics.mean(latencies) / 1000,
        "latency_p95_s": percentile(latencies, 0.95) / 1000,
        "tokens_per_question": statistics.mean(
            r["input_tokens"] + r["output_tokens"] for r in records
        ),
        "cost_per_question": statistics.mean(costs) if known_cost else None,
    }


def by_group(records: list[dict[str, Any]], key: str) -> dict[str, float]:
    groups: dict[str, list] = defaultdict(list)
    for r in records:
        groups[r[key]].append(r)
    return {name: rate(rs) for name, rs in sorted(groups.items())}


def pareto_front(summaries: dict[str, dict[str, Any]]) -> list[str]:
    """Models for which no other model is both at least as accurate and at most as costly."""
    priced = {m: s for m, s in summaries.items() if s["cost_per_question"] is not None}
    front = []
    for model, s in priced.items():
        dominated = any(
            o["accuracy"] >= s["accuracy"]
            and o["cost_per_question"] <= s["cost_per_question"]
            and (o["accuracy"], -o["cost_per_question"]) != (s["accuracy"], -s["cost_per_question"])
            for other, o in priced.items()
            if other != model
        )
        if not dominated:
            front.append(model)
    return front


def render(records: list[dict[str, Any]]) -> str:
    models: dict[str, list] = defaultdict(list)
    for r in records:
        models[r["model"]].append(r)
    summaries = {m: summarize_model(rs) for m, rs in models.items()}
    front = pareto_front(summaries)

    lines = [
        "# Résultats de l'évaluation",
        "",
        "| Modèle | Runs | Précision | Exécution | SQL valide | Refus corrects | "
        "Latence moy. (p95) | Tokens/question | Coût/question | Pareto |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for model, s in sorted(summaries.items(), key=lambda item: -item[1]["accuracy"]):
        cost = "n/a" if s["cost_per_question"] is None else f"${s['cost_per_question']:.5f}"
        lines.append(
            f"| {model} | {s['runs']} | {s['accuracy']:.1%} ± {s['accuracy_std']:.1%} "
            f"| {s['execution_accuracy']:.1%} | {s['valid_sql_rate']:.1%} "
            f"| {s['refusal_accuracy']:.1%} "
            f"| {s['latency_avg_s']:.1f} s ({s['latency_p95_s']:.1f} s) "
            f"| {s['tokens_per_question']:,.0f} | {cost} | {'✅' if model in front else ''} |"
        )

    for key, title in [("category", "Par catégorie"), ("difficulty", "Par difficulté")]:
        groups = {m: by_group(rs, key) for m, rs in models.items()}
        names = sorted({name for g in groups.values() for name in g})
        lines += ["", f"## {title}", "", "| " + key + " | " + " | ".join(groups) + " |"]
        lines.append("|---" * (len(groups) + 1) + "|")
        for name in names:
            cells = " | ".join(f"{g.get(name, 0):.0%}" for g in groups.values())
            lines.append(f"| {name} | {cells} |")

    failures = [r for r in records if not r["correct"]]
    lines += ["", f"## Échecs ({len(failures)})", ""]
    for r in failures:
        lines.append(f"- `{r['id']}` ({r['model']}, run {r['run']}): status={r['status']}")
    return "\n".join(lines) + "\n"


def print_summary(paths: list[Path]) -> None:
    report = render(load_records(paths))
    sys.stdout.reconfigure(encoding="utf-8")  # Windows consoles default to cp1252
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(report, encoding="utf-8")
    print(report.split("## Échecs")[0])
    print(f"Full report: {REPORT_PATH}")


def main() -> None:
    paths = [Path(p) for p in sys.argv[1:]] or sorted(RESULTS_DIR.glob("*.jsonl"))
    if not paths:
        raise SystemExit("No results found. Run `make eval` first.")
    print_summary(paths)


if __name__ == "__main__":
    main()
