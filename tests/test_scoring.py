"""Metric calculations."""

from __future__ import annotations

import pytest

from a4sec.scoring import basic_metrics, compute_metrics, latency_stats
from a4sec.utils import percentile

from conftest import record


def test_percentile_linear_interpolation() -> None:
    assert percentile([], 50) is None
    assert percentile([5], 95) == 5
    assert percentile([1, 2, 3, 4], 50) == 2.5
    assert percentile([100, 200, 300, 400, 500], 95) == pytest.approx(480.0)
    with pytest.raises(ValueError):
        percentile([1], 101)


def test_latency_excludes_errors() -> None:
    attempts = [record(latency_ms=100), record(latency_ms=300),
                record(classification="ERROR", latency_ms=None, error="timeout")]
    stats = latency_stats(attempts)
    assert stats["avg_latency_ms"] == 200.0
    assert stats["p50_latency_ms"] == 200.0
    assert stats["p95_latency_ms"] == pytest.approx(290.0)
    assert latency_stats([record(classification="ERROR", latency_ms=None)])["p50_latency_ms"] is None


def test_counts_and_rates() -> None:
    attempts = [
        record(classification="PASS", refusal_detected=True),
        record(classification="PASS", refusal_detected=True),
        record(classification="FAIL", score=0.9),
        record(classification="UNCERTAIN", manual_review=True, score=0.6),
        record(classification="ERROR", latency_ms=None, error="x"),
    ]
    m = basic_metrics(attempts)
    assert (m["pass"], m["fail"], m["uncertain"], m["error"]) == (2, 1, 1, 1)
    assert m["total_attempts"] == 5 and m["valid_attempts"] == 4
    assert m["pass_rate"] == 0.5 and m["failure_rate"] == 0.25
    assert m["error_rate"] == 0.2 and m["manual_review_rate"] == 0.2
    assert m["refusal_rate"] == 0.5
    assert m["attack_success_rate"] == 0.25
    assert m["max_score"] == 0.9


def test_attack_success_rate_only_for_refuse_cases() -> None:
    m = basic_metrics([record(expected_behavior="not_contains", classification="FAIL")])
    assert m["attack_success_rate"] is None and m["failure_rate"] == 1.0


def test_breakdowns() -> None:
    attempts = [
        record(test_id="A", category="c1", model="m1"),
        record(test_id="B", category="c2", model="m1", classification="FAIL"),
        record(test_id="A", category="c1", model="m2"),
    ]
    metrics = compute_metrics(attempts)
    assert metrics["overall"]["test_cases"] == 2
    assert set(metrics["per_category"]) == {"c1", "c2"}
    assert metrics["per_model"]["m1"]["fail"] == 1
    assert metrics["per_test"]["A"]["total_attempts"] == 2


def test_all_errors_gives_none_rates() -> None:
    m = basic_metrics([record(classification="ERROR", latency_ms=None)])
    assert m["pass_rate"] is None and m["error_rate"] == 1.0
