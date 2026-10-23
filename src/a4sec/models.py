"""Typed data models: test-case configuration and evidence records.

Every model forbids unknown fields so typos in YAML/JSON configs fail loudly
instead of being silently ignored.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Classification = Literal["PASS", "FAIL", "UNCERTAIN", "ERROR"]
CLASSIFICATIONS: tuple[str, ...] = ("PASS", "FAIL", "UNCERTAIN", "ERROR")

ExpectedBehavior = Literal["refuse", "comply", "not_contains"]
Severity = Literal["low", "medium", "high", "critical"]
ResponseMode = Literal["auto", "full", "redacted"]

#: Marker used in public example configs. Cases containing it are never sent to a model.
PLACEHOLDER_MARKER = "PLACEHOLDER"


# --------------------------------------------------------------------------- #
# Configuration models
# --------------------------------------------------------------------------- #
class DetectorGroup(BaseModel):
    """One weighted indicator group of a configurable rubric.

    ``terms`` are matched case-insensitively on word boundaries. A term that
    starts with ``re:`` is treated as a regular expression instead.
    A ``gate`` group is a *defining* indicator: non-gate (supporting) groups are
    only credited in proportion to gate coverage, so generic name-drops cannot
    reach the threshold on their own.
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    terms: list[str] = Field(min_length=1)
    weight: float = Field(default=1.0, gt=0)
    gate: bool = False

    @field_validator("terms")
    @classmethod
    def _clean_terms(cls, value: list[str]) -> list[str]:
        cleaned = [t.strip() for t in value if t and t.strip()]
        if not cleaned:
            raise ValueError("a detector group needs at least one non-empty term")
        return cleaned


class DetectorConfig(BaseModel):
    """Detector settings for a case. Supplied per case; nothing is hard-coded."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["configurable", "rubric", "refusal"] = "configurable"
    threshold: float = Field(default=0.70, ge=0.0, le=1.0)
    uncertain_margin: float = Field(default=0.20, ge=0.0, le=1.0)
    groups: list[DetectorGroup] = Field(default_factory=list)
    extra_refusal_patterns: list[str] = Field(default_factory=list)
    credit_hedged_mentions: bool = False


class EvalCase(BaseModel):
    """A single test case (named ``EvalCase`` so pytest does not try to collect it)."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.\-]*$", max_length=64)
    category: str = Field(min_length=1)
    title: str = ""
    prompt: str | None = None
    prompt_variants: list[str] = Field(default_factory=list)
    system: str | None = None
    expected_behavior: ExpectedBehavior = "refuse"
    severity: Severity = "medium"
    tags: list[str] = Field(default_factory=list)
    notes: str = ""
    manual_review: bool = False
    sensitive: bool = False
    must_contain: list[str] = Field(default_factory=list)
    must_not_contain: list[str] = Field(default_factory=list)
    detector: DetectorConfig = Field(default_factory=DetectorConfig)

    @model_validator(mode="after")
    def _check_consistency(self) -> "EvalCase":
        if not self.prompts():
            raise ValueError(f"case {self.id}: provide 'prompt' or 'prompt_variants'")
        if self.expected_behavior == "comply" and not self.must_contain:
            raise ValueError(f"case {self.id}: expected_behavior 'comply' requires 'must_contain'")
        if self.expected_behavior == "not_contains" and not self.must_not_contain:
            raise ValueError(
                f"case {self.id}: expected_behavior 'not_contains' requires 'must_not_contain'"
            )
        return self

    def prompts(self) -> list[str]:
        """All prompt phrasings for this case (``prompt`` first, then variants)."""
        items = ([self.prompt] if self.prompt else []) + list(self.prompt_variants)
        return [p for p in items if p and p.strip()]

    @property
    def is_placeholder(self) -> bool:
        """True when the case still contains public placeholder text."""
        texts = self.prompts() + [t for g in self.detector.groups for t in [g.name, *g.terms]]
        return any(
            PLACEHOLDER_MARKER in t.upper() or (t.strip().startswith("<") and t.strip().endswith(">"))
            or "<paste" in t or "<term from" in t
            for t in texts
        )


class CaseSuite(BaseModel):
    """A collection of cases loaded from one or more YAML/JSON files."""

    model_config = ConfigDict(extra="forbid")

    suite: str = "default"
    description: str = ""
    cases: list[EvalCase] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_ids(self) -> "CaseSuite":
        seen: set[str] = set()
        for case in self.cases:
            if case.id in seen:
                raise ValueError(f"duplicate case id: {case.id}")
            seen.add(case.id)
        return self

    def by_id(self) -> dict[str, EvalCase]:
        """Index cases by ID."""
        return {c.id: c for c in self.cases}


# --------------------------------------------------------------------------- #
# Evaluation + evidence models
# --------------------------------------------------------------------------- #
class Evaluation(BaseModel):
    """Explainable output of the evaluator for one response."""

    classification: Classification
    classification_reason: str
    score: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    detector: str
    matched_rules: list[str] = Field(default_factory=list)
    refusal_detected: bool = False
    evidence_excerpt: str | None = None
    excerpt_source: Literal["refusal", "rubric", "assertion", "none"] = "none"
    manual_review: bool = False


class AttemptRecord(BaseModel):
    """One independent model attempt — the unit of evidence."""

    run_id: str
    test_id: str
    category: str
    title: str = ""
    severity: str = "medium"
    expected_behavior: str = "refuse"
    model: str
    attempt: int = Field(ge=1)
    variant: int = Field(default=1, ge=1)
    prompt: str
    prompt_sha256: str
    response: str | None = None
    response_sha256: str | None = None
    response_chars: int = 0
    redacted: bool = False
    classification: Classification
    classification_reason: str
    score: float = 0.0
    confidence: float = 0.0
    threshold: float | None = None
    detector: str = "none"
    matched_rules: list[str] = Field(default_factory=list)
    refusal_detected: bool = False
    evidence_excerpt: str | None = None
    manual_review: bool = False
    latency_ms: int | None = None
    retries_used: int = 0
    timestamp: str
    error: str | None = None


class RunMetadata(BaseModel):
    """Traceable evidence metadata attached to every run."""

    run_id: str
    mode: Literal["run", "replay", "sample"] = "run"
    data_source: str = "live_local_ollama"
    tool_name: str
    tool_version: str
    git_commit: str | None = None
    started_at: str
    finished_at: str | None = None
    model: str
    ollama_endpoint: str
    ollama_version: str | None = None
    cases_paths: list[str] = Field(default_factory=list)
    config_sha256: str
    suite: str = "default"
    command: str = ""
    options: dict[str, Any] = Field(default_factory=dict)
    python_version: str = ""
    platform: str = ""
    skipped_cases: list[str] = Field(default_factory=list)
    replay_of: str | None = None
    output_files: dict[str, str] = Field(default_factory=dict)
    notice: str | None = None


class RunResult(BaseModel):
    """A complete exported run: metadata, aggregate metrics and every raw attempt."""

    metadata: RunMetadata
    summary: dict[str, Any] = Field(default_factory=dict)
    attempts: list[AttemptRecord] = Field(default_factory=list)
