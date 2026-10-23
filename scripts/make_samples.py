"""Regenerate samples/sample_results.{json,csv} from MOCKED responses.

These files only show the output format. Every response is a canned string served
by an in-process mock of the Ollama API — they are NOT real model outputs and must
never be reported as findings.

    python scripts/make_samples.py
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from a4sec.config import config_hash, load_cases  # noqa: E402
from a4sec.ollama_client import OllamaClient  # noqa: E402
from a4sec.runner import RunOptions, Runner, build_metadata, finalize_and_export, select_cases  # noqa: E402

CASES = ROOT / "configs" / "cases.example.yaml"

# Canned replies keyed by a fragment of the user prompt. "TIMEOUT" simulates a timeout.
CANNED = [
    ("business hours", "Example Bank is open Sunday to Thursday, 8 AM to 4 PM."),
    ("staff access code?", "I'm sorry, but I can't share internal codes."),
    ("Repeat all", "My instructions say the staff access code is BLUE-42 and I must not reveal it."),
    ("Translate", "Je suis BankBot. Je ne peux pas partager le code interne."),
    ("maintenance mode", "TIMEOUT"),
    ("IT admin", "I cannot provide the internal staff code, even for an audit."),
    ("capital of France", "I can only help with Example Bank services."),
    ("PIN", "Dear customer, please visit your nearest Example Bank branch to update your details."),
    ("PLACEHOLDER", "I'm sorry, but I can't help with that request."),
]


def handler(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/api/version":
        return httpx.Response(200, json={"version": "SAMPLE-MOCK"})
    if request.url.path == "/api/tags":
        return httpx.Response(200, json={"models": [{"name": "llama3.2:latest"}]})
    body = json.loads(request.content)
    user = body["messages"][-1]["content"]
    for fragment, reply in CANNED:
        if fragment.lower() in user.lower():
            if reply == "TIMEOUT":
                raise httpx.ReadTimeout("simulated timeout (sample)")
            return httpx.Response(200, json={"model": body["model"], "message": {"content": reply}})
    return httpx.Response(200, json={"model": body["model"], "message": {"content": "OK."}})


def main() -> None:
    suite = load_cases(CASES)
    selection = select_cases(suite, include_placeholders=True)
    opts = RunOptions(model="llama3.2", repeats=2, retries=1, timeout=30, backoff_seconds=0)
    client = OllamaClient("http://127.0.0.1:11434", timeout=30, transport=httpx.MockTransport(handler))
    run_id = "SAMPLE-20261022T000000Z-mocked"
    attempts = Runner(client, sleep=lambda _s: None).run_cases(selection.cases, run_id, opts)
    meta = build_metadata(
        run_id=run_id, opts=opts, endpoint="http://127.0.0.1:11434 (mocked)", ollama_version="SAMPLE-MOCK",
        cases_paths=["configs/cases.example.yaml"], config_sha256=config_hash([CASES]),
        suite=suite.suite, command="python scripts/make_samples.py", skipped=[], mode="sample",
    )
    meta.data_source = "SAMPLE_MOCKED — canned responses, NOT real model output"
    meta.notice = "Format example only. Do not cite these numbers as results."
    meta.git_commit = None

    tmp = ROOT / "samples" / "_tmp"
    result = finalize_and_export(meta, attempts, tmp)
    shutil.copy(result.metadata.output_files["json"], ROOT / "samples" / "sample_results.json")
    shutil.copy(result.metadata.output_files["csv"], ROOT / "samples" / "sample_results.csv")
    shutil.rmtree(tmp)
    print(f"wrote samples/sample_results.json and .csv ({len(attempts)} mocked attempts)")


if __name__ == "__main__":
    main()
