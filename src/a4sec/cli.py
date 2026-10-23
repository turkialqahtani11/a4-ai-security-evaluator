"""Command-line interface: doctor, run, compare, replay, summarize.

Exit codes:
  0 success
  1 run completed but a ``--fail-on`` classification was observed (useful in CI / regression)
  2 environment or configuration problem (Ollama down, model missing, bad config, ...)
"""

from __future__ import annotations

import platform
import shlex
import sys
from pathlib import Path
from typing import Annotated, Optional

import typer
import yaml
from rich.console import Console
from rich.table import Table

from a4sec import TOOL_NAME, __version__
from a4sec.compare import comparison_markdown, compare_models
from a4sec.config import ConfigError, config_hash, load_cases, load_models, resolve_endpoint
from a4sec.evidence import find_garak_python, new_run_id, run_version_command
from a4sec.exporters import ResultsError, dump_json, load_runs, render_summary_markdown, write_rows_csv
from a4sec.models import AttemptRecord, CaseSuite, RunResult
from a4sec.ollama_client import OllamaClient, OllamaError, model_available
from a4sec.runner import (
    RunOptions, Runner, build_metadata, finalize_and_export, prompt_drift, regression_suite,
    select_cases, select_replay_ids,
)
from a4sec.scoring import compute_metrics
from a4sec.utils import fmt_ms, fmt_pct, is_local_endpoint

app = typer.Typer(
    name=TOOL_NAME,
    help="Local, auditable AI security evaluation against Ollama models (PSU ASCL Day 4 / A4).",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()
err = Console(stderr=True)

DEFAULT_CASES = Path("configs/cases.example.yaml")
DEFAULT_MODELS = Path("configs/models.yaml")
DEFAULT_OUTPUT = Path("reports")
STYLE = {"PASS": "green", "FAIL": "red", "UNCERTAIN": "yellow", "ERROR": "magenta"}

# --------------------------------------------------------------------------- #
# Shared option types
# --------------------------------------------------------------------------- #
CasesOpt = Annotated[list[Path], typer.Option("--cases", "-c", help="YAML/JSON case file(s); repeat to merge.")]
EndpointOpt = Annotated[Optional[str], typer.Option("--endpoint", help="Ollama URL (default: env or http://127.0.0.1:11434).")]
RepeatsOpt = Annotated[int, typer.Option("--repeats", "-n", min=1, help="Attempts per case/variant.")]
TimeoutOpt = Annotated[float, typer.Option("--timeout", min=1, help="Per-request timeout in seconds.")]
RetriesOpt = Annotated[int, typer.Option("--retries", min=0, help="Retries on timeout/connection/5xx errors.")]
TempOpt = Annotated[float, typer.Option("--temperature", min=0.0, max=2.0, help="Sampling temperature.")]
SeedOpt = Annotated[Optional[int], typer.Option("--seed", help="Sampling seed (passed to Ollama options).")]
OutOpt = Annotated[Path, typer.Option("--output-dir", "-o", help="Folder for json/, csv/, evidence/.")]
ModeOpt = Annotated[str, typer.Option("--response-mode", help="auto (redact sensitive cases) | full | redacted.")]
IdsOpt = Annotated[Optional[list[str]], typer.Option("--id", help="Only run these test IDs (repeatable).")]
TagsOpt = Annotated[Optional[list[str]], typer.Option("--tag", help="Only run cases with this tag (repeatable).")]
FailOnOpt = Annotated[Optional[list[str]], typer.Option("--fail-on", help="Exit 1 if any attempt has this class (e.g. FAIL).")]
RemoteOpt = Annotated[bool, typer.Option("--allow-remote", help="Allow a non-local Ollama endpoint (off by default).")]
PlaceholderOpt = Annotated[bool, typer.Option("--include-placeholders", help="Also send placeholder cases (normally skipped).")]


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"{TOOL_NAME} {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[bool, typer.Option("--version", callback=_version_callback, is_eager=True,
                                          help="Show version and exit.")] = False,
) -> None:
    """a4sec — automated AI security testing against local Ollama models."""


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _fatal(message: str, code: int = 2) -> typer.Exit:
    err.print(f"[bold red]error:[/] {message}")
    return typer.Exit(code)


def _check_endpoint(endpoint: str, allow_remote: bool) -> None:
    if not is_local_endpoint(endpoint) and not allow_remote:
        raise _fatal(f"endpoint {endpoint} is not local. a4sec targets local Ollama only; "
                     "pass --allow-remote if you are authorized to test it.")


def _load_suite(cases: list[Path]) -> CaseSuite:
    try:
        return load_cases(cases)
    except ConfigError as exc:
        raise _fatal(str(exc)) from exc


def _preflight(client: OllamaClient, models: list[str]) -> str:
    """Fail clearly if Ollama is down or a model is not installed. Returns the Ollama version."""
    try:
        version = client.version()
        installed = client.list_models()
    except OllamaError as exc:
        raise _fatal(f"{exc}\nHint: run `ollama serve` (or start the Ollama app) and retry.") from exc
    missing = [m for m in models if not model_available(m, installed)]
    if missing:
        raise _fatal(f"model(s) not installed locally: {', '.join(missing)}. "
                     f"Install with: {' && '.join('ollama pull ' + m for m in missing)}")
    return version


def _progress(record: AttemptRecord) -> None:
    style = STYLE[record.classification]
    lat = f"{record.latency_ms} ms" if record.latency_ms is not None else "-"
    flag = " [yellow]review[/]" if record.manual_review else ""
    console.print(f"  {record.test_id:<22} v{record.variant} #{record.attempt:<2} "
                  f"[{style}]{record.classification:<9}[/] {lat:>9}{flag}")


def _print_summary(result: RunResult) -> None:
    m = result.summary["overall"]
    table = Table(title=f"Run {result.metadata.run_id} — {result.metadata.model}", show_lines=False)
    for col in ("Cases", "Attempts", "PASS", "FAIL", "UNCERTAIN", "ERROR", "Refusal", "Review", "Avg", "p50", "p95"):
        table.add_column(col, justify="right")
    table.add_row(
        str(m["test_cases"]), str(m["total_attempts"]), f"[green]{m['pass']}[/]", f"[red]{m['fail']}[/]",
        f"[yellow]{m['uncertain']}[/]", f"[magenta]{m['error']}[/]", fmt_pct(m["refusal_rate"]),
        fmt_pct(m["manual_review_rate"]), fmt_ms(m["avg_latency_ms"]), fmt_ms(m["p50_latency_ms"]),
        fmt_ms(m["p95_latency_ms"]),
    )
    console.print(table)
    per_cat = Table(title="Per category")
    for col in ("Category", "Attempts", "PASS", "FAIL", "UNCERTAIN", "ERROR", "Failure rate"):
        per_cat.add_column(col, justify="right" if col != "Category" else "left")
    for name, c in result.summary["per_category"].items():
        per_cat.add_row(name, str(c["total_attempts"]), str(c["pass"]), str(c["fail"]),
                        str(c["uncertain"]), str(c["error"]), fmt_pct(c["failure_rate"]))
    console.print(per_cat)
    for key, path in result.metadata.output_files.items():
        console.print(f"  {key:<8} {path}")


def _execute(
    *, suite: CaseSuite, cases_paths: list[Path], model: str, endpoint: str, opts: RunOptions,
    ids: list[str] | None, tags: list[str] | None, include_placeholders: bool, output_dir: Path,
    client: OllamaClient, ollama_version: str, mode: str = "run", replay_of: str | None = None,
) -> RunResult:
    try:
        selection = select_cases(suite, ids=ids, tags=tags, include_placeholders=include_placeholders)
    except ValueError as exc:
        raise _fatal(str(exc)) from exc
    for note in selection.skipped:
        console.print(f"[yellow]skipped[/] {note}")
    if not selection.cases:
        raise _fatal("no runnable cases after filtering (placeholders are skipped by default). "
                     "Copy configs/instructor_cases.local.yaml.example to configs/instructor_cases.local.yaml "
                     "and fill it from your authorized course materials.")

    run_id = new_run_id("replay-" if mode == "replay" else "")
    metadata = build_metadata(
        run_id=run_id, opts=opts, endpoint=endpoint, ollama_version=ollama_version,
        cases_paths=[str(p) for p in cases_paths], config_sha256=config_hash(cases_paths),
        suite=suite.suite, command=shlex.join(["a4sec", *sys.argv[1:]]),
        skipped=selection.skipped, mode=mode, replay_of=replay_of,
    )
    n_prompts = sum(len(c.prompts()) for c in selection.cases)
    console.print(f"[bold]{run_id}[/] model=[cyan]{model}[/] cases={len(selection.cases)} "
                  f"prompts={n_prompts} repeats={opts.repeats} -> {n_prompts * opts.repeats} attempts")
    attempts = Runner(client, progress=_progress).run_cases(selection.cases, run_id, opts)
    result = finalize_and_export(metadata, attempts, output_dir)
    _print_summary(result)
    return result


def _exit_for(results: list[RunResult], fail_on: list[str] | None) -> None:
    if not fail_on:
        return
    wanted = {f.upper() for f in fail_on}
    hits = [a for r in results for a in r.attempts if a.classification in wanted]
    if hits:
        console.print(f"[red]{len(hits)} attempt(s) classified as {', '.join(sorted(wanted))} -> exit 1[/]")
        raise typer.Exit(1)


def _make_opts(model: str, repeats: int, retries: int, timeout: float, temperature: float,
               seed: int | None, response_mode: str) -> RunOptions:
    if response_mode not in {"auto", "full", "redacted"}:
        raise _fatal("--response-mode must be auto, full or redacted")
    if response_mode == "full":
        console.print("[yellow]warning:[/] --response-mode full stores raw responses for sensitive cases. "
                      "Keep reports/ out of git (it is .gitignored) and do not publish them.")
    return RunOptions(model=model, repeats=repeats, retries=retries, timeout=timeout,
                      temperature=temperature, seed=seed, response_mode=response_mode)  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #
@app.command()
def doctor(
    model: Annotated[str, typer.Option("--model", "-m", help="Model that must be installed.")] = "llama3.2",
    endpoint: EndpointOpt = None,
    cases: Annotated[Optional[list[Path]], typer.Option("--cases", "-c", help="Case file(s) to validate.")] = None,
    garak_python: Annotated[Optional[str], typer.Option("--garak-python", help="Python of the Garak venv.")] = None,
    skip_tools: Annotated[bool, typer.Option("--skip-tools", help="Skip Promptfoo/Garak version checks.")] = False,
) -> None:
    """Check Python, Ollama, installed models, Promptfoo, Garak and config files."""
    endpoint = resolve_endpoint(endpoint)
    table = Table(title=f"{TOOL_NAME} {__version__} — environment check")
    table.add_column("Check")
    table.add_column("Status")
    table.add_column("Detail", overflow="fold")
    mandatory_ok = True

    def row(name: str, ok: bool | None, detail: str, mandatory: bool = False) -> None:
        nonlocal mandatory_ok
        status = "[green]OK[/]" if ok else ("[red]MISSING[/]" if mandatory else "[yellow]optional[/]")
        if ok is None:
            status = "[yellow]WARN[/]"
        if mandatory and not ok:
            mandatory_ok = False
        table.add_row(name, status, detail)

    py_ok = sys.version_info >= (3, 10)
    row("Python", py_ok, f"{platform.python_version()} ({sys.executable})", mandatory=True)
    row("Endpoint is local", is_local_endpoint(endpoint), endpoint)

    installed: list[str] = []
    with OllamaClient(endpoint, timeout=10) as client:
        try:
            row("Ollama reachable", True, f"version {client.version()}", mandatory=True)
            installed = client.list_models()
            row("Installed models", bool(installed), ", ".join(installed) or "none — run `ollama pull llama3.2`")
        except OllamaError as exc:
            row("Ollama reachable", False, f"{exc}", mandatory=True)
    row(f"Model '{model}'", model_available(model, installed),
        "installed" if model_available(model, installed) else f"run `ollama pull {model}`", mandatory=True)
    if DEFAULT_MODELS.exists():
        try:
            for tag in load_models(DEFAULT_MODELS):
                if tag != model:
                    ok = model_available(tag, installed)
                    row(f"Comparison model '{tag}'", ok, "installed" if ok else f"optional: `ollama pull {tag}`")
        except ConfigError as exc:
            row("models.yaml", None, str(exc))

    if not skip_tools:
        row("Promptfoo", bool(v := run_version_command(["promptfoo", "--version"], timeout=60)),
            v or "not found — `npm install -g promptfoo`")
        gp = find_garak_python(garak_python)
        row("Garak", bool(g := run_version_command([gp, "-m", "garak", "--version"], timeout=120)),
            (g or "not found — install in .venv-garak or pass --garak-python") + f" ({gp})")

    for path in cases or [DEFAULT_CASES]:
        try:
            suite = load_cases(path)
            placeholders = sum(1 for c in suite.cases if c.is_placeholder)
            row(f"Cases {path}", True, f"{len(suite.cases)} cases ({placeholders} placeholder)")
        except ConfigError as exc:
            row(f"Cases {path}", False, str(exc).splitlines()[0], mandatory=bool(cases))
    local_cfg = Path("configs/instructor_cases.local.yaml")
    row("Instructor local config", local_cfg.exists() or None,
        str(local_cfg) if local_cfg.exists() else "not created yet (needed for real BENCH-* runs)")
    row("Output folder", True, str(DEFAULT_OUTPUT.resolve()))

    console.print(table)
    if not mandatory_ok:
        raise _fatal("a mandatory dependency is missing (see table above).")
    console.print("[green]All mandatory checks passed.[/]")


@app.command()
def run(
    cases: CasesOpt = [DEFAULT_CASES],  # noqa: B006 - typer needs a literal default
    model: Annotated[str, typer.Option("--model", "-m", help="Local Ollama model tag.")] = "llama3.2",
    repeats: RepeatsOpt = 3,
    timeout: TimeoutOpt = 120.0,
    retries: RetriesOpt = 2,
    temperature: TempOpt = 0.0,
    seed: SeedOpt = None,
    output_dir: OutOpt = DEFAULT_OUTPUT,
    endpoint: EndpointOpt = None,
    response_mode: ModeOpt = "auto",
    ids: IdsOpt = None,
    tags: TagsOpt = None,
    fail_on: FailOnOpt = None,
    allow_remote: RemoteOpt = False,
    include_placeholders: PlaceholderOpt = False,
) -> None:
    """Run test cases against one local Ollama model and export JSON + CSV evidence."""
    endpoint = resolve_endpoint(endpoint)
    _check_endpoint(endpoint, allow_remote)
    suite = _load_suite(cases)
    opts = _make_opts(model, repeats, retries, timeout, temperature, seed, response_mode)
    with OllamaClient(endpoint, timeout=timeout) as client:
        version = _preflight(client, [model])
        result = _execute(suite=suite, cases_paths=cases, model=model, endpoint=endpoint, opts=opts,
                          ids=ids, tags=tags, include_placeholders=include_placeholders,
                          output_dir=output_dir, client=client, ollama_version=version)
    _exit_for([result], fail_on)


@app.command()
def compare(
    results: Annotated[Optional[list[Path]], typer.Option("--results", "-r", help="Existing result JSON files (skip running).")] = None,
    models: Annotated[Optional[list[str]], typer.Option("--model", "-m", help="Model(s) to run; default: configs/models.yaml.")] = None,
    cases: CasesOpt = [DEFAULT_CASES],  # noqa: B006
    repeats: RepeatsOpt = 3,
    timeout: TimeoutOpt = 120.0,
    retries: RetriesOpt = 2,
    temperature: TempOpt = 0.0,
    seed: SeedOpt = None,
    output_dir: OutOpt = DEFAULT_OUTPUT,
    endpoint: EndpointOpt = None,
    response_mode: ModeOpt = "auto",
    ids: IdsOpt = None,
    tags: TagsOpt = None,
    allow_remote: RemoteOpt = False,
    include_placeholders: PlaceholderOpt = False,
) -> None:
    """Compare models: run the same cases on each model, or load existing result files."""
    runs: list[RunResult]
    if results:
        try:
            runs = load_runs(results)
        except ResultsError as exc:
            raise _fatal(str(exc)) from exc
    else:
        try:
            model_list = models or load_models(DEFAULT_MODELS)
        except ConfigError as exc:
            raise _fatal(f"{exc} (or pass --model twice)") from exc
        if len(model_list) < 2:
            raise _fatal("compare needs at least two models (e.g. -m llama3.2 -m qwen2.5:3b)")
        endpoint = resolve_endpoint(endpoint)
        _check_endpoint(endpoint, allow_remote)
        suite = _load_suite(cases)
        runs = []
        with OllamaClient(endpoint, timeout=timeout) as client:
            version = _preflight(client, model_list)
            for model in model_list:
                opts = _make_opts(model, repeats, retries, timeout, temperature, seed, response_mode)
                runs.append(_execute(suite=suite, cases_paths=cases, model=model, endpoint=endpoint,
                                     opts=opts, ids=ids, tags=tags, include_placeholders=include_placeholders,
                                     output_dir=output_dir, client=client, ollama_version=version))
    try:
        comparison = compare_models(runs)
    except ValueError as exc:
        raise _fatal(str(exc)) from exc

    table = Table(title="Model comparison")
    for col in ("Model", "Attempts", "Refusal", "Failure", "Uncertain", "Review", "Error", "Avg", "p50", "p95"):
        table.add_column(col, justify="right" if col != "Model" else "left")
    for r in comparison["rows"]:
        table.add_row(r["model"], str(r["total_attempts"]), fmt_pct(r["refusal_rate"]),
                      fmt_pct(r["failure_rate"]), fmt_pct(r["uncertain_rate"]),
                      fmt_pct(r["manual_review_rate"]), fmt_pct(r["error_rate"]),
                      fmt_ms(r["avg_latency_ms"]), fmt_ms(r["p50_latency_ms"]), fmt_ms(r["p95_latency_ms"]))
    console.print(table)

    cmp_id = new_run_id("compare-")
    paths = {
        "json": dump_json(comparison, output_dir / "json" / f"{cmp_id}.json"),
        "csv": write_rows_csv(comparison["rows"], output_dir / "csv" / f"{cmp_id}.csv"),
        "markdown": output_dir / f"{cmp_id}.md",
    }
    paths["markdown"].parent.mkdir(parents=True, exist_ok=True)
    paths["markdown"].write_text(comparison_markdown(comparison), encoding="utf-8")
    for key, path in paths.items():
        console.print(f"  {key:<8} {path}")


@app.command()
def replay(
    results: Annotated[Path, typer.Option("--results", "-r", help="Prior result JSON file.")],
    cases: CasesOpt = [DEFAULT_CASES],  # noqa: B006
    status: Annotated[list[str], typer.Option("--status", help="Replay tests with these classes.")] = ["FAIL", "UNCERTAIN"],  # noqa: B006
    ids: IdsOpt = None,
    model: Annotated[Optional[str], typer.Option("--model", "-m", help="Override model (default: prior run's).")] = None,
    repeats: RepeatsOpt = 3,
    timeout: TimeoutOpt = 120.0,
    retries: RetriesOpt = 2,
    temperature: Annotated[Optional[float], typer.Option("--temperature", help="Default: prior run's.")] = None,
    seed: SeedOpt = None,
    output_dir: OutOpt = DEFAULT_OUTPUT,
    endpoint: EndpointOpt = None,
    response_mode: ModeOpt = "auto",
    export_regression: Annotated[Optional[Path], typer.Option("--export-regression", help="Also save the selected cases as a reusable regression YAML.")] = None,
    list_only: Annotated[bool, typer.Option("--list", help="Only list what would be replayed.")] = False,
    fail_on: FailOnOpt = None,
    allow_remote: RemoteOpt = False,
) -> None:
    """Re-run previously FAILED/UNCERTAIN (or chosen) test IDs as regression tests."""
    try:
        prior = load_runs([results])[0]
    except ResultsError as exc:
        raise _fatal(str(exc)) from exc
    try:
        replay_ids = select_replay_ids(prior, statuses=status, test_ids=ids)
    except ValueError as exc:
        raise _fatal(str(exc)) from exc
    if not replay_ids:
        console.print(f"[green]Nothing to replay:[/] no attempts with status {', '.join(status)} in {results}.")
        return
    console.print(f"Replaying from [bold]{prior.metadata.run_id}[/]: {', '.join(replay_ids)}")
    suite = _load_suite(cases)

    if export_regression:
        try:
            reg = regression_suite(suite, replay_ids, prior.metadata.run_id)
        except ValueError as exc:
            raise _fatal(str(exc)) from exc
        export_regression.parent.mkdir(parents=True, exist_ok=True)
        export_regression.write_text(
            "# Regression suite generated by `a4sec replay` — may contain local instructor text; keep private.\n"
            + yaml.safe_dump(reg.model_dump(exclude_defaults=True), sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
        console.print(f"  regression cases -> {export_regression}")
    if list_only:
        return

    selected = [c for c in suite.cases if c.id in replay_ids]
    for warning in prompt_drift(prior, selected):
        console.print(f"[yellow]warning:[/] {warning}")
    prior_opts = prior.metadata.options
    model = model or prior.metadata.model
    temp = temperature if temperature is not None else float(prior_opts.get("temperature", 0.0))
    seed = seed if seed is not None else prior_opts.get("seed")
    endpoint = resolve_endpoint(endpoint)
    _check_endpoint(endpoint, allow_remote)
    opts = _make_opts(model, repeats, retries, timeout, temp, seed, response_mode)
    with OllamaClient(endpoint, timeout=timeout) as client:
        version = _preflight(client, [model])
        result = _execute(suite=suite, cases_paths=cases, model=model, endpoint=endpoint, opts=opts,
                          ids=replay_ids, tags=None, include_placeholders=False, output_dir=output_dir,
                          client=client, ollama_version=version, mode="replay",
                          replay_of=prior.metadata.run_id)

    before = {t: prior.summary.get("per_test", {}).get(t, {}) for t in replay_ids}
    after = result.summary["per_test"]
    table = Table(title="Regression: before vs after")
    for col in ("Test ID", "Before FAIL", "Before UNCERTAIN", "After FAIL", "After UNCERTAIN", "Status"):
        table.add_column(col)
    for t in replay_ids:
        b, a = before.get(t, {}), after.get(t, {})
        still = a.get("fail", 0) + a.get("uncertain", 0)
        table.add_row(t, str(b.get("fail", "?")), str(b.get("uncertain", "?")), str(a.get("fail", 0)),
                      str(a.get("uncertain", 0)), "[red]FAILING[/]" if still else "[green]RESOLVED[/]")
    console.print(table)
    _exit_for([result], fail_on)


@app.command()
def summarize(
    results: Annotated[list[Path], typer.Argument(help="One or more result JSON files.")],
    output: Annotated[Optional[Path], typer.Option("--output", "-o", help="Markdown file to write.")] = None,
) -> None:
    """Combine result files into a Markdown summary for the PDF report."""
    try:
        runs = load_runs(results)
    except ResultsError as exc:
        raise _fatal(str(exc)) from exc
    combined = compute_metrics([a for r in runs for a in r.attempts])
    markdown = render_summary_markdown(runs, combined)
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(markdown, encoding="utf-8")
        console.print(f"summary -> {output}")
    else:
        console.print(markdown, markup=False, highlight=False)
