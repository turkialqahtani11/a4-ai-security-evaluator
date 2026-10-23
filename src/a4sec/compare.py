"""Model comparison (option C): the same cases across several local models."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from a4sec.models import AttemptRecord, RunResult
from a4sec.scoring import basic_metrics
from a4sec.utils import fmt_ms, fmt_pct

COMPARE_FIELDS = (
    "total_attempts", "valid_attempts", "pass", "fail", "uncertain", "error",
    "pass_rate", "refusal_rate", "failure_rate", "uncertain_rate", "manual_review_rate",
    "error_rate", "attack_success_rate", "avg_latency_ms", "p50_latency_ms", "p95_latency_ms",
)


def _by_model(attempts: list[AttemptRecord]) -> dict[str, list[AttemptRecord]]:
    groups: dict[str, list[AttemptRecord]] = defaultdict(list)
    for a in attempts:
        groups[a.model].append(a)
    return dict(groups)


def compare_models(runs: list[RunResult]) -> dict[str, Any]:
    """Per-model metric rows plus a per-test pass-rate matrix.

    Only test IDs present for *every* model are used in the matrix so the
    comparison is like-for-like; the rest are listed under ``not_shared``.
    """
    attempts = [a for r in runs for a in r.attempts]
    grouped = _by_model(attempts)
    if len(grouped) < 2:
        raise ValueError(f"comparison needs at least two models; found: {', '.join(grouped) or 'none'}")

    rows = []
    for model, items in sorted(grouped.items()):
        m = basic_metrics(items)
        rows.append({"model": model, **{k: m[k] for k in COMPARE_FIELDS}})

    test_sets = [{a.test_id for a in items} for items in grouped.values()]
    shared = sorted(set.intersection(*test_sets))
    not_shared = sorted(set.union(*test_sets) - set(shared))

    matrix: list[dict[str, Any]] = []
    for test_id in shared:
        row: dict[str, Any] = {"test_id": test_id}
        for model, items in sorted(grouped.items()):
            m = basic_metrics([a for a in items if a.test_id == test_id])
            row[f"{model} pass_rate"] = m["pass_rate"]
            row[f"{model} fail"] = m["fail"]
        matrix.append(row)

    return {
        "models": sorted(grouped),
        "run_ids": [r.metadata.run_id for r in runs],
        "rows": rows,
        "per_test": matrix,
        "shared_tests": shared,
        "not_shared": not_shared,
    }


def comparison_markdown(comparison: dict[str, Any]) -> str:
    """Render a comparison as Markdown tables."""
    out = ["# a4sec — Model Comparison", "",
           "Runs: " + ", ".join(f"`{r}`" for r in comparison["run_ids"]), "",
           "| Model | Attempts | Refusal rate | Failure rate | Uncertain | Manual review | Error rate | "
           "Avg latency | p50 | p95 |",
           "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for r in comparison["rows"]:
        out.append(
            f"| {r['model']} | {r['total_attempts']} | {fmt_pct(r['refusal_rate'])} | "
            f"{fmt_pct(r['failure_rate'])} | {fmt_pct(r['uncertain_rate'])} | "
            f"{fmt_pct(r['manual_review_rate'])} | {fmt_pct(r['error_rate'])} | "
            f"{fmt_ms(r['avg_latency_ms'])} | {fmt_ms(r['p50_latency_ms'])} | {fmt_ms(r['p95_latency_ms'])} |"
        )
    if comparison["per_test"]:
        models = comparison["models"]
        out += ["", "## Pass rate per shared test ID", "",
                "| Test ID | " + " | ".join(models) + " |", "|---|" + "---:|" * len(models)]
        for row in comparison["per_test"]:
            out.append(f"| {row['test_id']} | " + " | ".join(
                fmt_pct(row[f"{m} pass_rate"]) for m in models) + " |")
    if comparison["not_shared"]:
        out += ["", "Tests not run on every model (excluded from the matrix): "
                + ", ".join(comparison["not_shared"])]
    return "\n".join(out) + "\n"
