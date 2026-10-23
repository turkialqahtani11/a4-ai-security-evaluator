"""Exports: JSON (full evidence), CSV (one row per attempt) and Markdown summaries."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Iterable

from pydantic import ValidationError

from a4sec.models import AttemptRecord, RunResult
from a4sec.utils import fmt_ms, fmt_pct

#: Required columns first (assignment spec), then extra audit columns.
CSV_COLUMNS: list[str] = [
    "run_id", "test_id", "category", "model", "attempt", "classification",
    "classification_reason", "score", "manual_review", "latency_ms", "timestamp", "error",
    # extra audit fields
    "variant", "title", "severity", "expected_behavior", "confidence", "threshold",
    "detector", "matched_rules", "refusal_detected", "retries_used", "redacted",
    "prompt_sha256", "response_sha256", "response_chars", "evidence_excerpt",
]


class ResultsError(Exception):
    """Raised when a results file cannot be read."""


def write_json(result: RunResult, path: Path) -> Path:
    """Write the full run (metadata + summary + every attempt) as pretty JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    return path


def _csv_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, list):
        return ";".join(str(v) for v in value)
    if isinstance(value, bool):
        return "true" if value else "false"
    return value


def write_csv(attempts: Iterable[AttemptRecord], path: Path) -> Path:
    """Write one CSV row per attempt with the required + audit columns."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for attempt in attempts:
            row = attempt.model_dump()
            writer.writerow({col: _csv_value(row.get(col)) for col in CSV_COLUMNS})
    return path


def load_run(path: Path | str) -> RunResult:
    """Load a JSON results file previously written by :func:`write_json`."""
    p = Path(path).expanduser()
    if not p.exists():
        raise ResultsError(f"results file not found: {p}")
    try:
        return RunResult.model_validate_json(p.read_text(encoding="utf-8"))
    except (ValidationError, ValueError) as exc:
        raise ResultsError(f"{p} is not an a4sec results JSON file: {exc}") from exc


def write_rows_csv(rows: list[dict[str, Any]], path: Path) -> Path:
    """Write arbitrary dict rows (used by comparison exports)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0].keys()) if rows else []
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: _csv_value(v) for k, v in row.items()})
    return path


# --------------------------------------------------------------------------- #
# Markdown summary
# --------------------------------------------------------------------------- #
def _metrics_row(name: str, m: dict[str, Any]) -> str:
    return (
        f"| {name} | {m['total_attempts']} | {m['pass']} | {m['fail']} | {m['uncertain']} | "
        f"{m['error']} | {fmt_pct(m['pass_rate'])} | {fmt_pct(m['failure_rate'])} | "
        f"{fmt_pct(m['refusal_rate'])} | {fmt_pct(m['manual_review_rate'])} | "
        f"{fmt_ms(m['avg_latency_ms'])} | {fmt_ms(m['p50_latency_ms'])} | {fmt_ms(m['p95_latency_ms'])} |"
    )


_TABLE_HEAD = (
    "| Group | Attempts | PASS | FAIL | UNCERTAIN | ERROR | Pass rate | Failure rate | "
    "Refusal rate | Manual review | Avg latency | p50 | p95 |\n"
    "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"
)


def render_summary_markdown(runs: list[RunResult], combined: dict[str, Any]) -> str:
    """Concise Markdown summary for the PDF report. Never includes raw responses."""
    out: list[str] = ["# a4sec — Results Summary", ""]
    sample = [r.metadata.run_id for r in runs if r.metadata.mode == "sample"]
    if sample:
        out += ["> **SAMPLE DATA** — produced from mocked responses, not from a real model run. "
                "Do not report these numbers as findings.", ""]

    out += ["## Runs", "", "| Run ID | Mode | Model | Ollama | Started (UTC) | Config SHA-256 | Tool |",
            "|---|---|---|---|---|---|---|"]
    for r in runs:
        m = r.metadata
        out.append(f"| `{m.run_id}` | {m.mode} | {m.model} | {m.ollama_version or 'n/a'} | "
                   f"{m.started_at} | `{m.config_sha256[:12]}` | {m.tool_name} {m.tool_version} |")
    first = runs[0].metadata.options if runs else {}
    if first:
        out += ["", "Options (first run): " + ", ".join(f"`{k}={v}`" for k, v in first.items())]

    out += ["", "## Overall", "", _TABLE_HEAD, _metrics_row("**All**", combined["overall"])]
    for section, title in (("per_model", "Per model"), ("per_category", "Per category"), ("per_test", "Per test ID")):
        out += ["", f"## {title}", "", _TABLE_HEAD]
        out += [_metrics_row(name, m) for name, m in combined[section].items()]

    asr = combined["overall"].get("attack_success_rate")
    out += ["", f"Attack success rate (FAIL / valid attempts on refuse-expected cases): {fmt_pct(asr)}"]

    attempts = [a for r in runs for a in r.attempts]
    flagged = [a for a in attempts if a.classification in {"FAIL", "UNCERTAIN"}]
    out += ["", "## FAIL / UNCERTAIN attempts (reasons only)", ""]
    if flagged:
        out += ["| Test | Model | Attempt | Variant | Class | Score | Reason |", "|---|---|---:|---:|---|---:|---|"]
        for a in flagged[:50]:
            reason = a.classification_reason.replace("|", "/")
            out.append(f"| {a.test_id} | {a.model} | {a.attempt} | {a.variant} | {a.classification} | "
                       f"{a.score:.2f} | {reason} |")
        if len(flagged) > 50:
            out.append(f"\n_{len(flagged) - 50} more omitted — see the JSON/CSV evidence._")
    else:
        out.append("None.")

    errors = [a for a in attempts if a.classification == "ERROR"]
    if errors:
        out += ["", f"## Errors ({len(errors)})", ""]
        out += [f"- {a.test_id} / {a.model} / attempt {a.attempt}: {a.error}" for a in errors[:20]]

    out += ["", "## Interpretation notes", "",
            "- Classifications come from transparent rule-based detectors; UNCERTAIN and low-confidence "
            "attempts are flagged for manual review.",
            "- A high pass rate on these cases does not prove the model is secure; it only shows the "
            "configured detectors did not fire on these prompts.",
            "- Raw responses are stored in the JSON evidence (redacted for sensitive cases by default)."]
    return "\n".join(out) + "\n"


def load_runs(paths: Iterable[Path | str]) -> list[RunResult]:
    """Load several results files, raising :class:`ResultsError` on the first bad one."""
    return [load_run(p) for p in paths]


def dump_json(data: Any, path: Path) -> Path:
    """Write any JSON-serialisable object."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return path
