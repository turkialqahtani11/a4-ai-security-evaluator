"""Runner, retries, timeouts, replay, comparison and CLI — all with a mocked Ollama."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from typer.testing import CliRunner

import a4sec.cli as cli
from a4sec.compare import compare_models, comparison_markdown
from a4sec.evidence import REDACTED_PROMPT, REDACTED_RESPONSE
from a4sec.exporters import load_run
from a4sec.models import CaseSuite, RunMetadata, RunResult
from a4sec.ollama_client import OllamaConnectionError, OllamaModelNotFoundError, model_available
from a4sec.runner import (
    RunOptions, Runner, build_metadata, finalize_and_export, prompt_drift, regression_suite,
    select_cases, select_replay_ids,
)
from a4sec.scoring import compute_metrics

from conftest import make_case, mock_client, record, scripted_handler

ROOT = Path(__file__).resolve().parents[1]


class SleepRecorder:
    def __init__(self) -> None:
        self.calls: list[float] = []

    def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)


def test_client_version_tags_and_model_matching() -> None:
    client = mock_client(scripted_handler(["hi"], models=["llama3.2:latest", "qwen2.5:3b"]))
    assert client.version() == "0.0.0-mock"
    installed = client.list_models()
    assert model_available("llama3.2", installed) and model_available("qwen2.5:3b", installed)
    assert not model_available("mistral", installed)


def test_repeats_and_variants_recorded_independently() -> None:
    case = make_case(prompt="one", prompt_variants=["two"])
    runner = Runner(mock_client(scripted_handler(["I can't help with that."])), sleep=SleepRecorder())
    records = runner.run_cases([case], "RUN", RunOptions(model="llama3.2", repeats=3))
    assert len(records) == 6
    assert [(r.variant, r.attempt) for r in records] == [(1, 1), (1, 2), (1, 3), (2, 1), (2, 2), (2, 3)]
    assert all(r.classification == "PASS" and r.latency_ms is not None for r in records)
    assert records[0].prompt_sha256 != records[3].prompt_sha256


def test_timeout_then_success_uses_retry() -> None:
    sleep = SleepRecorder()
    handler = scripted_handler([httpx.ReadTimeout("slow"), "I cannot assist with that."])
    runner = Runner(mock_client(handler), sleep=sleep)
    rec = runner.run_attempt(make_case(), "p", run_id="R", attempt=1, variant=1,
                             opts=RunOptions(model="llama3.2", retries=2, backoff_seconds=0.5))
    assert rec.classification == "PASS"
    assert rec.retries_used == 1
    assert sleep.calls == [0.5]


def test_persistent_connection_error_becomes_error_record() -> None:
    sleep = SleepRecorder()
    runner = Runner(mock_client(scripted_handler([httpx.ConnectError("refused")])), sleep=sleep)
    rec = runner.run_attempt(make_case(), "p", run_id="R", attempt=1, variant=1,
                             opts=RunOptions(model="llama3.2", retries=2, backoff_seconds=1.0))
    assert rec.classification == "ERROR"
    assert "OllamaConnectionError" in (rec.error or "")
    assert rec.latency_ms is None and rec.retries_used == 2
    assert sleep.calls == [1.0, 2.0]  # exponential backoff


def test_timeout_error_after_all_retries() -> None:
    runner = Runner(mock_client(scripted_handler([httpx.ReadTimeout("slow")])), sleep=SleepRecorder())
    rec = runner.run_attempt(make_case(), "p", run_id="R", attempt=1, variant=1,
                             opts=RunOptions(model="llama3.2", retries=1))
    assert rec.classification == "ERROR" and "timed out" in (rec.error or "")


def test_model_not_found_is_not_retried() -> None:
    sleep = SleepRecorder()
    resp = httpx.Response(404, json={"error": "model 'nope' not found"})
    runner = Runner(mock_client(scripted_handler([resp])), sleep=sleep)
    rec = runner.run_attempt(make_case(), "p", run_id="R", attempt=1, variant=1,
                             opts=RunOptions(model="nope", retries=3))
    assert rec.classification == "ERROR" and rec.retries_used == 0 and sleep.calls == []
    with pytest.raises(OllamaModelNotFoundError):
        mock_client(scripted_handler([resp])).chat("nope", [{"role": "user", "content": "x"}])


def test_connection_error_raised_by_client() -> None:
    client = mock_client(scripted_handler([httpx.ConnectError("refused")]))
    with pytest.raises(OllamaConnectionError, match="ollama serve"):
        client.chat("llama3.2", [{"role": "user", "content": "x"}])


def test_sensitive_case_is_redacted_but_hashed() -> None:
    case = make_case(sensitive=True)
    text = "Use alphazine and betanol at 120 units."
    runner = Runner(mock_client(scripted_handler([text])), sleep=SleepRecorder())
    rec = runner.run_attempt(case, "secret prompt", run_id="R", attempt=1, variant=1,
                             opts=RunOptions(model="llama3.2"))
    assert rec.classification == "FAIL"
    assert rec.prompt == REDACTED_PROMPT and rec.response == REDACTED_RESPONSE
    assert rec.redacted and rec.evidence_excerpt is None  # rubric excerpt suppressed
    assert rec.response_sha256 and rec.response_chars == len(text)
    full = runner.run_attempt(case, "secret prompt", run_id="R", attempt=1, variant=1,
                              opts=RunOptions(model="llama3.2", response_mode="full"))
    assert full.response == text and not full.redacted


def test_system_prompt_and_options_sent() -> None:
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={"message": {"content": "ok"}})

    case = make_case(system="SYS", expected_behavior="not_contains", must_not_contain=["X9"], detector={})
    Runner(mock_client(handler)).run_attempt(case, "hi", run_id="R", attempt=1, variant=1,
                                            opts=RunOptions(model="m", temperature=0.2, seed=7))
    body = seen[0]
    assert body["messages"][0] == {"role": "system", "content": "SYS"}
    assert body["options"] == {"temperature": 0.2, "seed": 7} and body["stream"] is False


def test_run_options_validation() -> None:
    with pytest.raises(ValueError):
        RunOptions(model="m", repeats=0)
    with pytest.raises(ValueError):
        RunOptions(model="m", retries=-1)


def test_select_cases_skips_placeholders(small_suite: CaseSuite) -> None:
    sel = select_cases(small_suite)
    assert [c.id for c in sel.cases] == ["R-1", "S-1"]
    assert sel.skipped and sel.skipped[0].startswith("P-1")
    assert [c.id for c in select_cases(small_suite, ids=["S-1"]).cases] == ["S-1"]
    with pytest.raises(ValueError, match="unknown test id"):
        select_cases(small_suite, ids=["NOPE"])


def _run_result(model: str, classes: list[str], run_id: str = "RUN-1") -> RunResult:
    attempts = [record(run_id=run_id, model=model, test_id=f"T-{i % 2}", attempt=i + 1,
                       classification=c, latency_ms=100 * (i + 1)) for i, c in enumerate(classes)]
    meta = RunMetadata(run_id=run_id, tool_name="a4sec", tool_version="1.0.0", started_at="t",
                       model=model, ollama_endpoint="http://127.0.0.1:11434", config_sha256="0" * 64,
                       options={"temperature": 0.0})
    return RunResult(metadata=meta, summary=compute_metrics(attempts), attempts=attempts)


def test_replay_selection() -> None:
    prior = _run_result("llama3.2", ["PASS", "FAIL", "PASS", "UNCERTAIN"])
    # T-1 has FAIL and UNCERTAIN; T-0 only PASS
    assert select_replay_ids(prior) == ["T-1"]
    assert select_replay_ids(prior, statuses=["PASS"]) == ["T-0"]
    assert select_replay_ids(prior, test_ids=["T-0"]) == ["T-0"]
    with pytest.raises(ValueError, match="not present"):
        select_replay_ids(prior, test_ids=["T-9"])


def test_prompt_drift_and_regression_suite(small_suite: CaseSuite) -> None:
    prior = _run_result("m", ["FAIL"])
    prior.attempts[0] = prior.attempts[0].model_copy(update={"test_id": "R-1", "prompt_sha256": "f" * 64})
    assert prompt_drift(prior, small_suite.cases) == ["R-1 variant 1: prompt changed since the prior run"]
    reg = regression_suite(small_suite, ["R-1"], "RUN-1")
    assert [c.id for c in reg.cases] == ["R-1"] and "regression" in reg.cases[0].tags
    with pytest.raises(ValueError):
        regression_suite(small_suite, ["ZZZ"], "RUN-1")


def test_model_comparison_aggregation() -> None:
    a = _run_result("llama3.2", ["PASS", "FAIL", "PASS", "PASS"], "R-A")
    b = _run_result("qwen2.5:3b", ["FAIL", "FAIL", "ERROR", "PASS"], "R-B")
    cmp = compare_models([a, b])
    rows = {r["model"]: r for r in cmp["rows"]}
    assert rows["llama3.2"]["failure_rate"] == 0.25
    assert rows["qwen2.5:3b"]["error_rate"] == 0.25
    assert rows["qwen2.5:3b"]["failure_rate"] == round(2 / 3, 4)
    assert rows["llama3.2"]["p50_latency_ms"] == 250.0
    assert cmp["shared_tests"] == ["T-0", "T-1"]
    assert "llama3.2" in comparison_markdown(cmp)
    with pytest.raises(ValueError, match="at least two models"):
        compare_models([a])


def test_finalize_and_export_writes_evidence(tmp_path: Path, small_suite: CaseSuite) -> None:
    opts = RunOptions(model="llama3.2", repeats=2)
    runner = Runner(mock_client(scripted_handler(["I can't help with that."])), sleep=SleepRecorder())
    sel = select_cases(small_suite)
    attempts = runner.run_cases(sel.cases, "RUN-X", opts)
    meta = build_metadata(run_id="RUN-X", opts=opts, endpoint="http://127.0.0.1:11434",
                          ollama_version="mock", cases_paths=["x.yaml"], config_sha256="c" * 64,
                          suite="unit", command="a4sec run", skipped=sel.skipped)
    result = finalize_and_export(meta, attempts, tmp_path)
    for key in ("json", "csv", "manifest"):
        assert Path(result.metadata.output_files[key]).exists()
    manifest = json.loads(Path(result.metadata.output_files["manifest"]).read_text())
    assert len(manifest["files"]["json"]["sha256"]) == 64
    loaded = load_run(result.metadata.output_files["json"])
    assert loaded.summary["overall"]["total_attempts"] == 4
    assert loaded.metadata.options["repeats"] == 2


# --------------------------------------------------------------------------- #
# CLI (mocked Ollama)
# --------------------------------------------------------------------------- #
@pytest.fixture
def patch_client(monkeypatch: pytest.MonkeyPatch):
    def install(handler):
        real = cli.OllamaClient

        def factory(base_url: str, timeout: float = 120.0, transport=None):
            return real(base_url, timeout=timeout, transport=httpx.MockTransport(handler))

        monkeypatch.setattr(cli, "OllamaClient", factory)
    return install


def test_cli_run_replay_compare_summarize(tmp_path: Path, patch_client, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(ROOT)
    patch_client(scripted_handler(["The staff code is BLUE-42."], models=["llama3.2:latest", "qwen2.5:3b"]))
    runner = CliRunner()
    out = tmp_path / "reports"

    res = runner.invoke(cli.app, ["run", "-m", "llama3.2", "-n", "2", "--id", "DEMO-SECRET-DIRECT",
                                  "-o", str(out), "--fail-on", "FAIL"])
    assert res.exit_code == 1, res.output  # FAIL observed + --fail-on FAIL
    run_file = next((out / "json").glob("*.json"))
    assert load_run(run_file).summary["overall"]["fail"] == 2

    res = runner.invoke(cli.app, ["replay", "-r", str(run_file), "-n", "1", "-o", str(out),
                                  "--export-regression", str(tmp_path / "regression.yaml")])
    assert res.exit_code == 0, res.output
    assert "FAILING" in res.output
    assert "DEMO-SECRET-DIRECT" in (tmp_path / "regression.yaml").read_text()

    res = runner.invoke(cli.app, ["compare", "-m", "llama3.2", "-m", "qwen2.5:3b", "-n", "1",
                                  "--id", "DEMO-SCOPE", "-o", str(out)])
    assert res.exit_code == 0, res.output
    assert list(out.glob("compare-*.md"))

    summary = tmp_path / "summary.md"
    res = runner.invoke(cli.app, ["summarize", str(run_file), "-o", str(summary)])
    assert res.exit_code == 0 and "# a4sec — Results Summary" in summary.read_text()


def test_cli_run_fails_clearly_when_ollama_down(patch_client, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(ROOT)

    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    patch_client(down)
    res = CliRunner().invoke(cli.app, ["run", "-m", "llama3.2"])
    assert res.exit_code == 2
    res = CliRunner().invoke(cli.app, ["doctor", "--skip-tools"])
    assert res.exit_code == 2


def test_cli_run_missing_model_and_remote_endpoint(patch_client, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(ROOT)
    patch_client(scripted_handler(["x"], models=["other:latest"]))
    assert CliRunner().invoke(cli.app, ["run", "-m", "llama3.2"]).exit_code == 2
    res = CliRunner().invoke(cli.app, ["run", "--endpoint", "http://example.com:11434"])
    assert res.exit_code == 2


def test_cli_doctor_ok(patch_client, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(ROOT)
    patch_client(scripted_handler(["x"]))
    res = CliRunner().invoke(cli.app, ["doctor", "--skip-tools"])
    assert res.exit_code == 0, res.output
