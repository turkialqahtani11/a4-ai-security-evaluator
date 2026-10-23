"""Aggregate metrics over raw attempt records.

Rate definitions (all documented in the README):

* ``pass_rate`` / ``failure_rate`` / ``uncertain_rate`` — over *valid* attempts
  (attempts that produced a model response, i.e. not ERROR).
* ``error_rate`` and ``manual_review_rate`` — over *all* attempts.
* ``refusal_rate`` — valid attempts where refusal language was detected.
* ``attack_success_rate`` — FAIL / valid attempts among cases whose expected
  behavior is ``refuse`` (handout definition: confirmed successful attempts
  divided by valid tested attempts). ``None`` when no such cases exist.
* Latency statistics use only valid attempts.
"""

from __future__ import annotations

from collections import defaultdict
from statistics import fmean
from typing import Any, Callable, Iterable

from a4sec.models import CLASSIFICATIONS, AttemptRecord
from a4sec.utils import percentile, safe_ratio


def latency_stats(attempts: Iterable[AttemptRecord]) -> dict[str, float | None]:
    """Average, p50, p95, min and max latency (ms) of valid attempts."""
    values = [a.latency_ms for a in attempts if a.classification != "ERROR" and a.latency_ms is not None]
    if not values:
        return {"avg_latency_ms": None, "p50_latency_ms": None, "p95_latency_ms": None,
                "min_latency_ms": None, "max_latency_ms": None}
    return {
        "avg_latency_ms": round(fmean(values), 1),
        "p50_latency_ms": round(percentile(values, 50) or 0.0, 1),
        "p95_latency_ms": round(percentile(values, 95) or 0.0, 1),
        "min_latency_ms": float(min(values)),
        "max_latency_ms": float(max(values)),
    }


def basic_metrics(attempts: list[AttemptRecord]) -> dict[str, Any]:
    """Counts, rates and latency for one group of attempts."""
    counts = {c: 0 for c in CLASSIFICATIONS}
    for a in attempts:
        counts[a.classification] += 1
    total = len(attempts)
    valid = [a for a in attempts if a.classification != "ERROR"]
    refuse_valid = [a for a in valid if a.expected_behavior == "refuse"]

    return {
        "test_cases": len({a.test_id for a in attempts}),
        "total_attempts": total,
        "valid_attempts": len(valid),
        "pass": counts["PASS"],
        "fail": counts["FAIL"],
        "uncertain": counts["UNCERTAIN"],
        "error": counts["ERROR"],
        "manual_review": sum(1 for a in attempts if a.manual_review),
        "pass_rate": safe_ratio(counts["PASS"], len(valid)),
        "failure_rate": safe_ratio(counts["FAIL"], len(valid)),
        "uncertain_rate": safe_ratio(counts["UNCERTAIN"], len(valid)),
        "error_rate": safe_ratio(counts["ERROR"], total),
        "manual_review_rate": safe_ratio(sum(1 for a in attempts if a.manual_review), total),
        "refusal_rate": safe_ratio(sum(1 for a in valid if a.refusal_detected), len(valid)),
        "attack_success_rate": safe_ratio(
            sum(1 for a in refuse_valid if a.classification == "FAIL"), len(refuse_valid)
        ),
        "mean_score": round(fmean([a.score for a in valid]), 4) if valid else None,
        "max_score": round(max(a.score for a in valid), 4) if valid else None,
        **latency_stats(attempts),
    }


def _group(attempts: list[AttemptRecord], key: Callable[[AttemptRecord], str]) -> dict[str, dict[str, Any]]:
    buckets: dict[str, list[AttemptRecord]] = defaultdict(list)
    for a in attempts:
        buckets[key(a)].append(a)
    return {k: basic_metrics(v) for k, v in sorted(buckets.items())}


def compute_metrics(attempts: list[AttemptRecord]) -> dict[str, Any]:
    """Overall metrics plus per-category, per-model and per-test-ID breakdowns."""
    return {
        "overall": basic_metrics(attempts),
        "per_category": _group(attempts, lambda a: a.category),
        "per_model": _group(attempts, lambda a: a.model),
        "per_test": _group(attempts, lambda a: a.test_id),
    }
