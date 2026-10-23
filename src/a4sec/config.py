"""Loading and validating YAML/JSON test-case and model configuration."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Iterable

import yaml
from pydantic import ValidationError

from a4sec.models import CaseSuite, EvalCase
from a4sec.utils import DEFAULT_OLLAMA_URL, sha256_bytes


class ConfigError(Exception):
    """Raised for any unreadable, malformed or invalid configuration file."""


def _read_structured(path: Path) -> Any:
    """Parse a YAML or JSON file, choosing the parser by extension."""
    if not path.exists():
        raise ConfigError(f"config file not found: {path}")
    if not path.is_file():
        raise ConfigError(f"not a file: {path}")
    text = path.read_text(encoding="utf-8")
    suffix = path.suffix.lower()
    try:
        if suffix == ".json":
            return json.loads(text)
        if suffix in {".yaml", ".yml"} or path.name.endswith((".yaml.example", ".yml.example")):
            return yaml.safe_load(text)
    except (json.JSONDecodeError, yaml.YAMLError) as exc:
        raise ConfigError(f"could not parse {path}: {exc}") from exc
    raise ConfigError(f"unsupported config extension for {path} (use .yaml, .yml or .json)")


def _format_validation_error(path: Path, exc: ValidationError) -> str:
    lines = [f"invalid test-case config {path}:"]
    for err in exc.errors():
        loc = ".".join(str(p) for p in err["loc"]) or "<root>"
        lines.append(f"  - {loc}: {err['msg']}")
    return "\n".join(lines)


def parse_suite(data: Any, source: Path | str = "<memory>") -> CaseSuite:
    """Validate already-parsed data. Accepts ``{cases: [...]}`` or a bare list of cases."""
    path = Path(source)
    if data is None:
        raise ConfigError(f"{path} is empty")
    if isinstance(data, list):
        data = {"cases": data}
    if not isinstance(data, dict):
        raise ConfigError(f"{path}: top level must be a mapping with 'cases' or a list of cases")
    if "cases" not in data:
        raise ConfigError(f"{path}: missing required key 'cases'")
    # Keys starting with "x-" are YAML-anchor helpers (e.g. a shared system prompt).
    data = {k: v for k, v in data.items() if not str(k).startswith("x-")}
    try:
        return CaseSuite.model_validate(data)
    except ValidationError as exc:
        raise ConfigError(_format_validation_error(path, exc)) from exc


def load_cases(paths: Path | str | Iterable[Path | str]) -> CaseSuite:
    """Load and merge one or more case files into a single validated suite.

    Merging lets a public example file and a private ``*.local.yaml`` instructor
    file be used together. Duplicate IDs across files are rejected.
    """
    if isinstance(paths, (str, Path)):
        paths = [paths]
    path_list = [Path(p).expanduser() for p in paths]
    if not path_list:
        raise ConfigError("no case files given")

    suites = [parse_suite(_read_structured(p), p) for p in path_list]
    if len(suites) == 1:
        return suites[0]
    merged: list[EvalCase] = [c for s in suites for c in s.cases]
    try:
        return CaseSuite(
            suite="+".join(s.suite for s in suites),
            description="merged suite",
            cases=merged,
        )
    except ValidationError as exc:
        raise ConfigError(_format_validation_error(Path("<merged>"), exc)) from exc


def config_hash(paths: Iterable[Path | str]) -> str:
    """SHA-256 over the raw bytes of every config file (order-sensitive)."""
    blob = b""
    for p in paths:
        path = Path(p).expanduser()
        blob += path.name.encode() + b"\0" + path.read_bytes() + b"\0"
    return sha256_bytes(blob)


def load_models(path: Path | str) -> list[str]:
    """Read the list of model tags from ``configs/models.yaml``."""
    data = _read_structured(Path(path))
    if not isinstance(data, dict) or not isinstance(data.get("models"), list):
        raise ConfigError(f"{path}: expected a mapping with a 'models' list")
    tags: list[str] = []
    for item in data["models"]:
        tag = item.get("tag") if isinstance(item, dict) else item
        if not isinstance(tag, str) or not tag.strip():
            raise ConfigError(f"{path}: every model needs a non-empty 'tag'")
        tags.append(tag.strip())
    return tags


def resolve_endpoint(cli_value: str | None = None) -> str:
    """CLI flag > ``A4SEC_OLLAMA_URL`` > ``OLLAMA_BASE_URL`` > ``OLLAMA_HOST`` > default."""
    for value in (
        cli_value,
        os.environ.get("A4SEC_OLLAMA_URL"),
        os.environ.get("OLLAMA_BASE_URL"),
        os.environ.get("OLLAMA_HOST"),
    ):
        if value and value.strip():
            value = value.strip().rstrip("/")
            if "://" not in value:
                value = "http://" + value
            return value
    return DEFAULT_OLLAMA_URL
