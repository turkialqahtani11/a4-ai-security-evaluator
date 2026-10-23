# A4 — Automated AI Security Testing

**Student:** Turki Alqahtani
**Course:** AI Security Training — Day 4 · ASCL, Prince Sultan University
**Date:** [INSERT DATE]
**Repository:** [INSERT GITHUB LINK] · **Video:** [INSERT DRIVE LINK]

> Fill every `[INSERT …]` with values you actually observed. Leave a section as "not run" rather
> than estimating. Numbers come from `a4sec summarize`, Promptfoo and Garak reports only.

---

## 1. Executive Summary

[INSERT 4–6 sentences: what was tested, on which local models, with which tools; the most
important observed result; the key finding; the mitigation and whether the re-test confirmed it.]

## 2. Scope and Authorization

- Authorized academic assignment (A4). Targets: local Ollama models only — `llama3.2`, `qwen2.5:3b`.
- Inputs: Day 4 companion configs and instructor-provided benchmark material.
- Out of scope: third-party/production systems, cloud model APIs.
- Sensitive benchmark text and responses are not reproduced in this report (hashes / IDs only).

## 3. Environment and Versions

Source: `python scripts/collect_environment.py -o reports/evidence/environment.json`

| Component | Version |
|---|---|
| OS / WSL | [INSERT] |
| Python | [INSERT] |
| Ollama | [INSERT] |
| Model tags (+ digest from `ollama list`) | [INSERT] |
| Node.js | [INSERT] |
| Promptfoo | [INSERT] |
| Garak | [INSERT] |
| a4sec version / git commit | [INSERT] |
| Hardware (CPU/GPU/RAM) | [INSERT] |
| Test date | [INSERT] |

## 4. Promptfoo — Deterministic Evaluation

- Command: `[INSERT EXACT COMMAND]`
- Config: `promptfooconfig.yaml` (T01–T06), repeats: 5, expected outputs: up to 30.

| Test | Intent | PASS | FAIL | Notes (assertion reason) |
|---|---|---:|---:|---|
| T01 | Business hours | [INSERT] | [INSERT] | [INSERT] |
| T02 | Direct code request | [INSERT] | [INSERT] | [INSERT] |
| T03 | Repeat instructions | [INSERT] | [INSERT] | [INSERT] |
| T04 | French translation (manual review) | [INSERT] | [INSERT] | [INSERT] |
| T05 | Fake administrator | [INSERT] | [INSERT] | [INSERT] |
| T06 | Unrelated geography | [INSERT] | [INSERT] | [INSERT] |
| **Total** | | [INSERT] | [INSERT] | Errors/skips: [INSERT] |

Possible false negatives observed: [INSERT].

## 5. Promptfoo — Red-Team Evaluation

- Plugins / strategies: [INSERT]
- Generated test count (verified `tests:` exists in `redteam.yaml`): [INSERT]
- Results: [INSERT PASS/FAIL per plugin/strategy]
- Example generated input and response for one FAIL: [INSERT — redact if sensitive]

## 6. Garak Evaluation

| Model | Probe | Detector | Generations | Pass rate | Hits | Report file |
|---|---|---|---:|---:|---:|---|
| llama3.2 | [INSERT] | [INSERT] | [INSERT] | [INSERT] | [INSERT] | [INSERT] |
| qwen2.5:3b | [INSERT] | [INSERT] | [INSERT] | [INSERT] | [INSERT] | [INSERT] |

Reviewed JSONL entries behind hits: [INSERT what was confirmed vs. detector noise].
(A probe pass rate is not a whole-model security score; a hit is not automatically an exploit.)

## 7. Three Instructor Benchmark Categories

Threshold: rubric score ≥ 70 % = FAIL. Prompts/responses stored as hashes.

| ID | Category | Model | Variants × repeats | PASS | FAIL | UNCERTAIN | ERROR | Max score | Tool |
|---|---|---|---|---:|---:|---:|---:|---:|---|
| BENCH-METH | Crystal Meth | llama3.2 | [INSERT] | [INSERT] | [INSERT] | [INSERT] | [INSERT] | [INSERT] | a4sec |
| BENCH-NERVE | Nerve Agent | llama3.2 | [INSERT] | [INSERT] | [INSERT] | [INSERT] | [INSERT] | [INSERT] | a4sec |
| BENCH-FENTANYL | Fentanyl | llama3.2 | [INSERT] | [INSERT] | [INSERT] | [INSERT] | [INSERT] | [INSERT] | a4sec |
| … | … | qwen2.5:3b | [INSERT] | | | | | | |
| (same IDs) | | both | | | | | | | Promptfoo rubric assertion |

Manual review of UNCERTAIN / low-confidence attempts: [INSERT outcome].

## 8. Custom Python Security Tool

`a4sec` — commands `doctor`, `run`, `compare`, `replay`, `summarize`. Inputs: YAML/JSON cases;
options for model, repeats, timeout, retries, temperature, seed. Output: per-attempt JSON/CSV with
classification, reason, score, confidence, latency, plus an evidence manifest.

## 9. Architecture

[INSERT the Mermaid diagram from the README as an image, plus 2–3 sentences.]

## 10. Test Methodology

- Cases: [INSERT number of demo + benchmark cases, variants]
- Repeats: [INSERT] · Temperature: [INSERT] · Seed: [INSERT] · Timeout: [INSERT] · Retries: [INSERT]
- Classification rules: refusal detector; weighted/gated rubric with ≥ 0.70 threshold and 0.20
  uncertainty band; required/forbidden-string detectors; manual review when UNCERTAIN, flagged, or confidence < 0.70.

## 11. Metrics and Results

Source: `a4sec summarize reports/json/<runs>.json -o reports/summary.md`

| Metric | Value |
|---|---|
| Test cases | [INSERT ACTUAL RESULT AFTER RUN] |
| Total attempts | [INSERT ACTUAL RESULT AFTER RUN] |
| PASS / FAIL / UNCERTAIN / ERROR | [INSERT ACTUAL RESULT AFTER RUN] |
| Pass rate / failure rate | [INSERT ACTUAL RESULT AFTER RUN] |
| Refusal rate | [INSERT ACTUAL RESULT AFTER RUN] |
| Attack success rate | [INSERT ACTUAL RESULT AFTER RUN] |
| Manual-review rate | [INSERT ACTUAL RESULT AFTER RUN] |
| Avg / p50 / p95 latency | [INSERT ACTUAL RESULT AFTER RUN] |

Per-category table: [INSERT from summary.md]

## 12. Model Comparison

Source: `reports/compare-<id>.md`

| Model | Attempts | Refusal | Failure | Uncertain | Error | Avg | p50 | p95 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| llama3.2 | [INSERT] | [INSERT] | [INSERT] | [INSERT] | [INSERT] | [INSERT] | [INSERT] | [INSERT] |
| qwen2.5:3b | [INSERT] | [INSERT] | [INSERT] | [INSERT] | [INSERT] | [INSERT] | [INSERT] | [INSERT] |

Interpretation: [INSERT].

## 13. Original Improvement(s)

- **A. Explainable scoring** — every attempt has matched rules, score, confidence, reason, excerpt, review flag.
- **B. Regression replay** — `a4sec replay` reruns FAIL/UNCERTAIN IDs and exports a regression YAML.
- **C. Model comparison** — `a4sec compare` across `llama3.2` and `qwen2.5:3b`.
- **D. Traceable evidence** — run ID, config SHA-256, versions, command, output hashes in a manifest.

[INSERT one example record (non-sensitive) showing these fields.]

## 14. Key Finding

| Field | Value |
|---|---|
| Title | [INSERT] |
| Test ID / tool | [INSERT] |
| Model + version | [INSERT] |
| Input reference | [INSERT prompt or prompt_sha256] |
| Observed response | [INSERT — redact if sensitive] |
| Classification + reason | [INSERT] |
| Reproducibility | [INSERT e.g. 4/5 attempts, replayed 8/10] |
| Evidence files | [INSERT paths] |

## 15. Impact

[INSERT what an attacker/user could achieve, who is affected, severity rationale.]

## 16. Root Cause

[INSERT — e.g. secret placed in the system prompt; instructions are not an access-control boundary.]

## 17. Mitigation

[INSERT a concrete backend control — e.g. remove secrets from the prompt, output filtering on the
server, policy classifier before returning responses — and/or an evaluation improvement.]

## 18. Regression / Re-Test

- Command: `a4sec replay --results [INSERT] --cases [INSERT] --repeats [INSERT]`
- Before vs after: [INSERT table from replay output]

## 19. Limitations and False Positives/Negatives

[INSERT observed false positives/negatives; reference README §20 limitations.]

## 20. Reproducibility

Exact commands, config SHA-256 values and run IDs: [INSERT]. Another person can reproduce with
the README steps and the same model tags.

## 21. Conclusion

[INSERT 3–4 sentences.]

## 22. Evidence Index

| # | Evidence | File / screenshot |
|---|---|---|
| E01 | Environment JSON | `reports/evidence/environment.json` |
| E02 | Promptfoo deterministic report | `reports/promptfoo/bankbot.{html,json,csv}` |
| E03 | Promptfoo red-team tests + report | `redteam.yaml`, `reports/promptfoo/redteam.*` |
| E04 | Promptfoo benchmark report | `reports/promptfoo/benchmarks.*` |
| E05 | Garak reports | `reports/garak/day4_*.report.{jsonl,html}` |
| E06 | a4sec runs | `reports/json/*.json`, `reports/csv/*.csv`, `reports/evidence/*_manifest.json` |
| E07 | Comparison | `reports/compare-*.md` |
| E08 | Replay | `reports/json/replay-*.json` |
| E09 | Screenshots S01–S16 | `docs/SCREENSHOT_CHECKLIST.md` |
