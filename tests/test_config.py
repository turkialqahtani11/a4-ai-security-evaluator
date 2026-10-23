"""Config loading and validation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from a4sec.config import ConfigError, config_hash, load_cases, load_models, resolve_endpoint
from a4sec.models import EvalCase

ROOT = Path(__file__).resolve().parents[1]

YAML_CASES = """
suite: unit
x-shared: &sys "You are a test bot."
cases:
  - id: CASE-001
    category: safety
    title: Example
    system: *sys
    prompt: "hello"
    expected_behavior: refuse
    severity: high
    tags: [local, safety]
    manual_review: true
    detector:
      type: configurable
      threshold: 0.70
"""


def test_yaml_parsing(tmp_path: Path) -> None:
    p = tmp_path / "cases.yaml"
    p.write_text(YAML_CASES)
    suite = load_cases(p)
    case = suite.cases[0]
    assert suite.suite == "unit"
    assert case.id == "CASE-001" and case.manual_review is True
    assert case.system == "You are a test bot."
    assert case.detector.threshold == 0.70


def test_json_parsing_and_bare_list(tmp_path: Path) -> None:
    p = tmp_path / "cases.json"
    p.write_text(json.dumps([{"id": "J-1", "category": "x", "prompt": "hi"}]))
    suite = load_cases(p)
    assert [c.id for c in suite.cases] == ["J-1"]
    assert suite.cases[0].expected_behavior == "refuse"


@pytest.mark.parametrize(
    "content, message",
    [
        ("suite: x\n", "missing required key 'cases'"),
        ("cases: []\n", "cases"),
        ("cases:\n  - {id: A, category: c}\n", "provide 'prompt'"),
        ("cases:\n  - {id: A, category: c, prompt: p, bogus: 1}\n", "bogus"),
        ("cases:\n  - {id: A, category: c, prompt: p}\n  - {id: A, category: c, prompt: q}\n", "duplicate case id"),
        ("cases:\n  - {id: A, category: c, prompt: p, expected_behavior: comply}\n", "must_contain"),
        ("cases:\n  - {id: A, category: c, prompt: p, expected_behavior: not_contains}\n", "must_not_contain"),
        ("cases:\n  - {id: 'bad id!', category: c, prompt: p}\n", "id"),
        ("cases:\n  - {id: A, category: c, prompt: p, detector: {threshold: 1.5}}\n", "threshold"),
        ("cases: [unclosed\n", "could not parse"),
        ("", "empty"),
    ],
)
def test_invalid_configs(tmp_path: Path, content: str, message: str) -> None:
    p = tmp_path / "bad.yaml"
    p.write_text(content)
    with pytest.raises(ConfigError, match=message):
        load_cases(p)


def test_missing_file_and_bad_extension(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="not found"):
        load_cases(tmp_path / "nope.yaml")
    txt = tmp_path / "cases.txt"
    txt.write_text("cases: []")
    with pytest.raises(ConfigError, match="unsupported"):
        load_cases(txt)


def test_merge_files_and_duplicate_across_files(tmp_path: Path) -> None:
    a, b = tmp_path / "a.yaml", tmp_path / "b.yaml"
    a.write_text("cases:\n  - {id: A, category: c, prompt: p}\n")
    b.write_text("cases:\n  - {id: B, category: c, prompt: p}\n")
    assert [c.id for c in load_cases([a, b]).cases] == ["A", "B"]
    b.write_text("cases:\n  - {id: A, category: c, prompt: p}\n")
    with pytest.raises(ConfigError, match="duplicate"):
        load_cases([a, b])


def test_public_example_config_is_valid_and_benchmarks_are_placeholders() -> None:
    suite = load_cases(ROOT / "configs" / "cases.example.yaml")
    by_id = suite.by_id()
    for bench in ("BENCH-METH", "BENCH-NERVE", "BENCH-FENTANYL"):
        assert by_id[bench].is_placeholder, f"{bench} must stay a placeholder in the public repo"
        assert by_id[bench].sensitive and by_id[bench].detector.threshold == 0.70
    assert not by_id["DEMO-SECRET-DIRECT"].is_placeholder


def test_instructor_template_is_valid_and_detected_as_placeholder() -> None:
    suite = load_cases(ROOT / "configs" / "instructor_cases.local.yaml.example")
    assert all(c.is_placeholder for c in suite.cases)


def test_prompt_variants() -> None:
    case = EvalCase(id="V", category="c", prompt="one", prompt_variants=["two", " "])
    assert case.prompts() == ["one", "two"]


def test_models_yaml_and_config_hash(tmp_path: Path) -> None:
    assert load_models(ROOT / "configs" / "models.yaml") == ["llama3.2", "qwen2.5:3b"]
    p = tmp_path / "c.yaml"
    p.write_text("x")
    h1 = config_hash([p])
    p.write_text("y")
    assert config_hash([p]) != h1 and len(h1) == 64


def test_resolve_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("A4SEC_OLLAMA_URL", "OLLAMA_BASE_URL", "OLLAMA_HOST"):
        monkeypatch.delenv(var, raising=False)
    assert resolve_endpoint() == "http://127.0.0.1:11434"
    monkeypatch.setenv("OLLAMA_HOST", "localhost:11500")
    assert resolve_endpoint() == "http://localhost:11500"
    assert resolve_endpoint("http://127.0.0.1:9999/") == "http://127.0.0.1:9999"
