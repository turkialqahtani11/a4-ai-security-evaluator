# Samples — FORMAT EXAMPLES ONLY

`sample_results.json` and `sample_results.csv` were produced by `python scripts/make_samples.py`,
which runs the real `a4sec` runner, evaluator and exporters against an **in-process mock of the
Ollama API that returns canned strings**.

- They are **not** model outputs and must **not** be reported as results.
- `metadata.mode` is `sample`, `metadata.data_source` says `SAMPLE_MOCKED`, and the run ID starts with `SAMPLE-`.
- Latencies are ~0 ms because no model ran.
- The BENCH-* records are placeholder cases answered with a canned refusal; their prompts and
  responses are redacted to show how sensitive cases are stored.
- The sample includes each classification: PASS, FAIL (a canned secret leak), UNCERTAIN (a
  canned non-refusal) and ERROR (a simulated timeout).

Real results are written to `reports/` when you run `a4sec run` against your local Ollama.
