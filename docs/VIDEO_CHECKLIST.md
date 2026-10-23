# Demonstration Video Checklist

Target length: **5–8 minutes**. Concise and technical. Record the terminal at a readable font size.
Do not show sensitive benchmark prompt text or harmful responses on screen.

| # | Segment | What to show / say | ~Time | Done |
|---|---|---|---|---|
| 1 | Project folder / GitHub | Repo page, folder tree, README headline | 0:20 | [ ] |
| 2 | Architecture | README Mermaid diagram: cases → runner → Ollama → evaluator → metrics → JSON/CSV; replay + compare | 0:40 | [ ] |
| 3 | `a4sec doctor` | Python, Ollama, models, Promptfoo, Garak checks | 0:30 | [ ] |
| 4 | One local evaluation run | `a4sec run -c configs/cases.example.yaml -m llama3.2 -n 3` (and/or the local benchmark file) | 1:00 | [ ] |
| 5 | Classification + reason | Point at one PASS, one FAIL/UNCERTAIN line and its `classification_reason` | 0:30 | [ ] |
| 6 | JSON + CSV evidence | Open the JSON record (run_id, hashes, matched_rules, latency) and the CSV | 0:40 | [ ] |
| 7 | Original feature | `a4sec compare -m llama3.2 -m qwen2.5:3b …` table | 0:40 | [ ] |
| 8 | Regression replay | `a4sec replay -r reports/json/<run>.json … --export-regression …` before/after | 0:40 | [ ] |
| 9 | Automated tests | `pytest -q` → all passing; mention mocked Ollama | 0:20 | [ ] |
| 10 | Code walkthrough | `evaluator.py` (`_evaluate_refuse`, `rubric_score` gating + hedge rule), `runner.py` (`run_attempt` retries), `evidence.py` (`apply_redaction`, manifest) | 1:30 | [ ] |
| 11 | Promptfoo/Garak evidence | `reports/promptfoo/*.html`, Garak `*.report.html` locations | 0:30 | [ ] |
| 12 | Submission artifacts | PDF, screenshots folder, repo link | 0:20 | [ ] |

## Talking points

- Why rule-based detectors: transparent and auditable; UNCERTAIN + confidence make their limits explicit.
- Why repeats: a single surprising response is not a repeatable finding.
- Why hashes for sensitive cases: evidence stays verifiable without republishing harmful content.
- Why local-only: endpoint check + no proxy; no cloud model APIs.

## Before uploading

- [ ] Audio clear, no notifications on screen
- [ ] No harmful content or private data visible
- [ ] Uploaded to Google Drive, sharing set to "Anyone with the link — Viewer" (or the instructors' accounts)
