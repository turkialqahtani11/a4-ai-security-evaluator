"""JSON / CSV / Markdown exports."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from a4sec.exporters import CSV_COLUMNS, ResultsError, load_run, render_summary_markdown, write_csv, write_json
from a4sec.models import RunMetadata, RunResult
from a4sec.scoring import compute_metrics

from conftest import record

REQUIRED = ["run_id", "test_id", "category", "model", "attempt", "classification",
            "classification_reason", "score", "manual_review", "latency_ms", "timestamp", "error"]


def _result(mode: str = "run") -> RunResult:
    attempts = [
        record(response="SECRET RESPONSE TEXT", matched_rules=["rubric:a", "rubric:b"]),
        record(attempt=2, classification="FAIL", classification_reason="score high", score=0.8),
        record(attempt=3, classification="ERROR", latency_ms=None, error="OllamaTimeoutError: t"),
    ]
    meta = RunMetadata(run_id="RUN-1", mode=mode, tool_name="a4sec", tool_version="1.0.0",
                       started_at="2026-10-22T00:00:00Z", model="llama3.2",
                       ollama_endpoint="http://127.0.0.1:11434", config_sha256="a" * 64)
    return RunResult(metadata=meta, summary=compute_metrics(attempts), attempts=attempts)


def test_json_round_trip(tmp_path: Path) -> None:
    path = write_json(_result(), tmp_path / "json" / "run.json")
    data = json.loads(path.read_text())
    for key in REQUIRED:
        assert key in data["attempts"][0]
    loaded = load_run(path)
    assert loaded.metadata.run_id == "RUN-1"
    assert len(loaded.attempts) == 3
    assert loaded.summary["overall"]["error"] == 1


def test_load_run_errors(tmp_path: Path) -> None:
    with pytest.raises(ResultsError, match="not found"):
        load_run(tmp_path / "missing.json")
    bad = tmp_path / "bad.json"
    bad.write_text('{"hello": 1}')
    with pytest.raises(ResultsError, match="not an a4sec"):
        load_run(bad)


def test_csv_export(tmp_path: Path) -> None:
    path = write_csv(_result().attempts, tmp_path / "csv" / "run.csv")
    with path.open(newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert list(rows[0].keys())[: len(REQUIRED)] == REQUIRED
    assert list(rows[0].keys()) == CSV_COLUMNS
    assert len(rows) == 3
    assert rows[0]["matched_rules"] == "rubric:a;rubric:b"
    assert rows[0]["manual_review"] == "false"
    assert rows[2]["latency_ms"] == "" and rows[2]["classification"] == "ERROR"
    assert "SECRET RESPONSE TEXT" not in path.read_text()  # CSV never carries raw responses


def test_markdown_summary_has_tables_and_no_raw_responses() -> None:
    result = _result(mode="sample")
    md = render_summary_markdown([result], compute_metrics(result.attempts))
    assert "SAMPLE DATA" in md
    assert "## Per category" in md and "## Per test ID" in md
    assert "score high" in md
    assert "SECRET RESPONSE TEXT" not in md
