"""Test execution: repeated attempts, retries, timeouts, evidence and regression replay."""

from __future__ import annotations

import platform
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Iterable

from a4sec import TOOL_NAME, __version__
from a4sec.evaluator import evaluate
from a4sec.evidence import apply_redaction, build_error_record, git_commit, write_manifest
from a4sec.exporters import write_csv, write_json
from a4sec.models import AttemptRecord, CaseSuite, EvalCase, ResponseMode, RunMetadata, RunResult
from a4sec.ollama_client import OllamaClient, OllamaError
from a4sec.scoring import compute_metrics
from a4sec.utils import sha256_text, utc_now_iso

ProgressFn = Callable[[AttemptRecord], None]


@dataclass
class RunOptions:
    """Execution settings recorded verbatim in the run metadata."""

    model: str
    repeats: int = 3
    retries: int = 2
    timeout: float = 120.0
    temperature: float = 0.0
    seed: int | None = None
    response_mode: ResponseMode = "auto"
    backoff_seconds: float = 1.0

    def __post_init__(self) -> None:
        if self.repeats < 1:
            raise ValueError("repeats must be >= 1")
        if self.retries < 0:
            raise ValueError("retries must be >= 0")
        if self.timeout <= 0:
            raise ValueError("timeout must be > 0")
        if not 0.0 <= self.temperature <= 2.0:
            raise ValueError("temperature must be between 0 and 2")


@dataclass
class CaseSelection:
    """Which cases to run and which were skipped (with reasons)."""

    cases: list[EvalCase]
    skipped: list[str] = field(default_factory=list)


def select_cases(
    suite: CaseSuite,
    ids: Iterable[str] | None = None,
    tags: Iterable[str] | None = None,
    include_placeholders: bool = False,
) -> CaseSelection:
    """Filter a suite by ID / tag and drop public placeholder cases.

    Placeholder cases (public example benchmarks) are never sent to a model unless
    explicitly requested, because their results would be meaningless.
    """
    id_set = {i.strip() for i in ids or [] if i.strip()}
    tag_set = {t.strip() for t in tags or [] if t.strip()}
    unknown = id_set - {c.id for c in suite.cases}
    if unknown:
        raise ValueError(f"unknown test id(s): {', '.join(sorted(unknown))}")

    chosen: list[EvalCase] = []
    skipped: list[str] = []
    for case in suite.cases:
        if id_set and case.id not in id_set:
            continue
        if tag_set and not tag_set & set(case.tags):
            continue
        if case.is_placeholder and not include_placeholders:
            skipped.append(f"{case.id}: placeholder content — supply the authorized local config")
            continue
        chosen.append(case)
    return CaseSelection(chosen, skipped)


class Runner:
    """Executes cases against one model and records every attempt independently."""

    def __init__(
        self,
        client: OllamaClient,
        sleep: Callable[[float], None] = time.sleep,
        progress: ProgressFn | None = None,
    ) -> None:
        self.client = client
        self.sleep = sleep
        self.progress = progress

    def run_attempt(
        self, case: EvalCase, prompt: str, *, run_id: str, attempt: int, variant: int, opts: RunOptions
    ) -> AttemptRecord:
        """Run one attempt with retry/backoff; never raises for model/transport errors."""
        messages = ([{"role": "system", "content": case.system}] if case.system else []) + [
            {"role": "user", "content": prompt}
        ]
        last_error = "unknown error"
        for try_index in range(opts.retries + 1):
            started = utc_now_iso()
            try:
                result = self.client.chat(opts.model, messages, temperature=opts.temperature, seed=opts.seed)
            except OllamaError as exc:
                last_error = f"{exc.__class__.__name__}: {exc}"
                if not exc.retryable or try_index == opts.retries:
                    return build_error_record(
                        run_id=run_id, case=case, model=opts.model, attempt=attempt, variant=variant,
                        prompt=prompt, error=last_error, retries_used=try_index,
                        mode=opts.response_mode, timestamp=started,
                    )
                self.sleep(opts.backoff_seconds * (2**try_index))
                continue

            evaluation = evaluate(case, result.text)
            stored_prompt, stored_response, excerpt, redacted = apply_redaction(
                case, prompt, result.text, evaluation, opts.response_mode
            )
            return AttemptRecord(
                run_id=run_id, test_id=case.id, category=case.category, title=case.title,
                severity=case.severity, expected_behavior=case.expected_behavior, model=opts.model,
                attempt=attempt, variant=variant, prompt=stored_prompt,
                prompt_sha256=sha256_text(prompt), response=stored_response,
                response_sha256=sha256_text(result.text), response_chars=len(result.text),
                redacted=redacted, classification=evaluation.classification,
                classification_reason=evaluation.classification_reason, score=evaluation.score,
                confidence=evaluation.confidence,
                threshold=case.detector.threshold if case.expected_behavior == "refuse" else None,
                detector=evaluation.detector, matched_rules=evaluation.matched_rules,
                refusal_detected=evaluation.refusal_detected, evidence_excerpt=excerpt,
                manual_review=evaluation.manual_review, latency_ms=result.latency_ms,
                retries_used=try_index, timestamp=started, error=None,
            )
        # Unreachable in practice; kept for type-checkers.
        return build_error_record(
            run_id=run_id, case=case, model=opts.model, attempt=attempt, variant=variant, prompt=prompt,
            error=last_error, retries_used=opts.retries, mode=opts.response_mode, timestamp=utc_now_iso(),
        )

    def run_cases(self, cases: list[EvalCase], run_id: str, opts: RunOptions) -> list[AttemptRecord]:
        """Run every prompt variant of every case ``opts.repeats`` times."""
        records: list[AttemptRecord] = []
        for case in cases:
            for variant, prompt in enumerate(case.prompts(), start=1):
                for attempt in range(1, opts.repeats + 1):
                    record = self.run_attempt(
                        case, prompt, run_id=run_id, attempt=attempt, variant=variant, opts=opts
                    )
                    records.append(record)
                    if self.progress:
                        self.progress(record)
        return records


def build_metadata(
    *, run_id: str, opts: RunOptions, endpoint: str, ollama_version: str | None,
    cases_paths: list[str], config_sha256: str, suite: str, command: str,
    skipped: list[str], mode: str = "run", replay_of: str | None = None,
) -> RunMetadata:
    """Assemble traceable run metadata (option D: evidence management)."""
    return RunMetadata(
        run_id=run_id, mode=mode, tool_name=TOOL_NAME, tool_version=__version__,
        git_commit=git_commit(Path(__file__).resolve().parent), started_at=utc_now_iso(),
        model=opts.model, ollama_endpoint=endpoint, ollama_version=ollama_version,
        cases_paths=cases_paths, config_sha256=config_sha256, suite=suite, command=command,
        options={k: v for k, v in asdict(opts).items() if k != "model"},
        python_version=platform.python_version(), platform=platform.platform(),
        skipped_cases=skipped, replay_of=replay_of,
    )


def finalize_and_export(metadata: RunMetadata, attempts: list[AttemptRecord], output_dir: Path) -> RunResult:
    """Compute metrics, write JSON + CSV + evidence manifest, and return the result."""
    metadata.finished_at = utc_now_iso()
    json_path = output_dir / "json" / f"{metadata.run_id}.json"
    csv_path = output_dir / "csv" / f"{metadata.run_id}.csv"
    manifest_path = output_dir / "evidence" / f"{metadata.run_id}_manifest.json"
    metadata.output_files = {"json": str(json_path), "csv": str(csv_path), "manifest": str(manifest_path)}

    result = RunResult(metadata=metadata, summary=compute_metrics(attempts), attempts=attempts)
    write_json(result, json_path)
    write_csv(attempts, csv_path)
    write_manifest(result, manifest_path)
    return result


# --------------------------------------------------------------------------- #
# Regression replay (option B)
# --------------------------------------------------------------------------- #
def select_replay_ids(
    prior: RunResult,
    statuses: Iterable[str] = ("FAIL", "UNCERTAIN"),
    test_ids: Iterable[str] | None = None,
) -> list[str]:
    """Test IDs to replay: explicit IDs (must exist in the prior run) or those with matching status."""
    prior_ids = {a.test_id for a in prior.attempts}
    explicit = [t.strip() for t in test_ids or [] if t.strip()]
    if explicit:
        missing = [t for t in explicit if t not in prior_ids]
        if missing:
            raise ValueError(f"test id(s) not present in prior run: {', '.join(missing)}")
        return sorted(set(explicit))
    wanted = {s.upper() for s in statuses}
    return sorted({a.test_id for a in prior.attempts if a.classification in wanted})


def prompt_drift(prior: RunResult, cases: list[EvalCase]) -> list[str]:
    """Warn when a case's prompt text changed since the prior run (hash comparison)."""
    prior_hashes: dict[tuple[str, int], str] = {
        (a.test_id, a.variant): a.prompt_sha256 for a in prior.attempts
    }
    warnings: list[str] = []
    for case in cases:
        for variant, prompt in enumerate(case.prompts(), start=1):
            old = prior_hashes.get((case.id, variant))
            if old and old != sha256_text(prompt):
                warnings.append(f"{case.id} variant {variant}: prompt changed since the prior run")
    return warnings


def regression_suite(suite: CaseSuite, ids: list[str], source_run: str) -> CaseSuite:
    """Build a reusable regression suite containing only ``ids``."""
    index = suite.by_id()
    missing = [i for i in ids if i not in index]
    if missing:
        raise ValueError(f"id(s) not found in cases file: {', '.join(missing)}")
    cases = [
        index[i].model_copy(update={"tags": sorted(set(index[i].tags) | {"regression"})})
        for i in ids
    ]
    return CaseSuite(
        suite=f"regression-from-{source_run}",
        description=f"Regression cases selected from run {source_run}",
        cases=cases,
    )
