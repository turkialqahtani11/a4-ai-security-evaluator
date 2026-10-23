"""Traceable evidence management: run IDs, hashes, environment and redaction.

Nothing here uses a shell. External tools are invoked with argument lists and
short timeouts, only to read their version strings.
"""

from __future__ import annotations

import json
import platform
import shutil
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from a4sec import TOOL_NAME, __version__
from a4sec.models import AttemptRecord, EvalCase, Evaluation, ResponseMode, RunResult
from a4sec.utils import sha256_bytes, sha256_text

REDACTED_PROMPT = "[REDACTED sensitive prompt — see prompt_sha256 and the local config]"
REDACTED_RESPONSE = "[REDACTED sensitive response — see response_sha256; rerun with --response-mode full for local review]"


def new_run_id(prefix: str = "") -> str:
    """Sortable, collision-resistant run identifier, e.g. ``20261023T101500Z-1a2b3c4d``."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{prefix}{stamp}-{uuid.uuid4().hex[:8]}"


def run_version_command(args: list[str], timeout: float = 30.0) -> str | None:
    """Run ``args`` (no shell) and return the first non-empty output line, or None."""
    if not args or not shutil.which(args[0]) and not Path(args[0]).exists():
        return None
    try:
        proc = subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    for line in (proc.stdout + "\n" + proc.stderr).splitlines():
        if line.strip():
            return line.strip()
    return None


def git_commit(cwd: Path | None = None) -> str | None:
    """Short git commit of the project, if it is a git checkout."""
    if not shutil.which("git"):
        return None
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5, check=False,
            cwd=str(cwd or Path.cwd()),
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.strip() or None


def find_garak_python(explicit: str | None = None) -> str:
    """Pick the interpreter that has Garak: explicit > ./.venv-garak > ~/DAY_4/.venv-garak > current."""
    if explicit:
        return str(Path(explicit).expanduser())
    for candidate in (Path(".venv-garak/bin/python"), Path.home() / "DAY_4/.venv-garak/bin/python"):
        if candidate.exists():
            return str(candidate)
    return sys.executable


def collect_environment(garak_python: str | None = None, include_tools: bool = True) -> dict[str, Any]:
    """Versions of Python, the OS and (optionally) Promptfoo / Garak / Ollama CLIs."""
    env: dict[str, Any] = {
        "tool": f"{TOOL_NAME} {__version__}",
        "git_commit": git_commit(),
        "python": platform.python_version(),
        "python_executable": sys.executable,
        "platform": platform.platform(),
        "collected_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    if include_tools:
        env["ollama_cli"] = run_version_command(["ollama", "--version"])
        env["node"] = run_version_command(["node", "--version"])
        env["promptfoo"] = run_version_command(["promptfoo", "--version"], timeout=60)
        gp = find_garak_python(garak_python)
        env["garak_python"] = gp
        env["garak"] = run_version_command([gp, "-m", "garak", "--version"], timeout=120)
    return env


def apply_redaction(
    case: EvalCase, prompt: str, response: str, evaluation: Evaluation, mode: ResponseMode
) -> tuple[str, str, str | None, bool]:
    """Decide what text is stored for an attempt.

    Returns ``(stored_prompt, stored_response, stored_excerpt, redacted)``.
    In ``auto`` mode, cases marked ``sensitive`` keep only hashes, rule names and
    (if present) a refusal excerpt — never a rubric excerpt from a harmful answer.
    """
    redact = mode == "redacted" or (mode == "auto" and case.sensitive)
    if not redact:
        return prompt, response, evaluation.evidence_excerpt, False
    excerpt = evaluation.evidence_excerpt if evaluation.excerpt_source == "refusal" else None
    return REDACTED_PROMPT, REDACTED_RESPONSE, excerpt, True


def build_error_record(
    *, run_id: str, case: EvalCase, model: str, attempt: int, variant: int, prompt: str,
    error: str, retries_used: int, mode: ResponseMode, timestamp: str, latency_ms: int | None = None,
) -> AttemptRecord:
    """Evidence record for an attempt that produced no valid model output."""
    redact = mode == "redacted" or (mode == "auto" and case.sensitive)
    return AttemptRecord(
        run_id=run_id, test_id=case.id, category=case.category, title=case.title,
        severity=case.severity, expected_behavior=case.expected_behavior, model=model,
        attempt=attempt, variant=variant,
        prompt=REDACTED_PROMPT if redact else prompt, prompt_sha256=sha256_text(prompt),
        redacted=redact, classification="ERROR",
        classification_reason=f"No valid model output: {error}",
        detector="none", manual_review=case.manual_review, latency_ms=latency_ms,
        retries_used=retries_used, timestamp=timestamp, error=error,
        threshold=case.detector.threshold if case.expected_behavior == "refuse" else None,
    )


def file_digest(path: Path) -> str:
    """SHA-256 of a file on disk."""
    return sha256_bytes(path.read_bytes())


def write_manifest(result: RunResult, path: Path) -> Path:
    """Write an evidence manifest: metadata, output file paths and their SHA-256 digests."""
    files = {
        name: {"path": p, "sha256": file_digest(Path(p)) if Path(p).exists() else None}
        for name, p in result.metadata.output_files.items()
    }
    manifest = {
        "run_id": result.metadata.run_id,
        "metadata": result.metadata.model_dump(),
        "overall": result.summary.get("overall", {}),
        "files": files,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return path
