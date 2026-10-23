# Screenshot Checklist (S01–S16)

Capture real terminal/browser screens only. Name files `S01_environment.png`, etc.
Make sure each screenshot shows the command **and** its output. Blur or crop any sensitive benchmark text.

| ID | What to capture | Command / location | Done |
|---|---|---|---|
| S01 | Environment / tool versions | `python scripts/collect_environment.py` or `node -v; python3 -V; ollama -v; promptfoo --version; python -m garak --version` | [ ] |
| S02 | Ollama model list | `ollama list` and `curl http://127.0.0.1:11434/api/tags` | [ ] |
| S03 | Promptfoo YAML validation | `promptfoo validate -c promptfooconfig.yaml` (+ `redteam_config.yaml`) | [ ] |
| S04 | Promptfoo deterministic evaluation | `promptfoo eval … --repeat 5` terminal + HTML report with one FAIL opened | [ ] |
| S05 | Promptfoo generated red-team tests | `grep -n 'tests:' redteam.yaml` + a few generated inputs in the editor | [ ] |
| S06 | Promptfoo red-team report | `promptfoo redteam report` / `redteam.html` | [ ] |
| S07 | Garak probe inventory | `python -m garak --list_probes` (and detectors/generators/buffs, `--plugin_info`) | [ ] |
| S08 | Garak scan command | the `python -m garak --target_type ollama.OllamaGeneratorChat …` run | [ ] |
| S09 | Garak raw/report output | `*.report.html` in browser + a `*.report.jsonl` entry behind a hit | [ ] |
| S10 | Custom CLI doctor command | `a4sec doctor --garak-python ~/DAY_4/.venv-garak/bin/python` | [ ] |
| S11 | Custom CLI benchmark run | `a4sec run -c configs/instructor_cases.local.yaml -m llama3.2 -n 5` (summary tables) | [ ] |
| S12 | JSON/CSV exports | one record in `reports/json/<run>.json` + the CSV opened | [ ] |
| S13 | Model comparison | `a4sec compare -m llama3.2 -m qwen2.5:3b …` table | [ ] |
| S14 | Regression replay | `a4sec replay -r reports/json/<run>.json …` before/after table | [ ] |
| S15 | pytest passing | `pytest -q` | [ ] |
| S16 | GitHub repository structure | repository page on GitHub (file tree + README) | [ ] |

## Captions

**S01 — Environment / tool versions**
Explanation: ____________________

**S02 — Ollama model list**
Explanation: ____________________

**S03 — Promptfoo YAML validation**
Explanation: ____________________

**S04 — Promptfoo deterministic evaluation**
Explanation: ____________________

**S05 — Promptfoo generated red-team tests**
Explanation: ____________________

**S06 — Promptfoo red-team report**
Explanation: ____________________

**S07 — Garak probe inventory**
Explanation: ____________________

**S08 — Garak scan command**
Explanation: ____________________

**S09 — Garak raw/report output**
Explanation: ____________________

**S10 — Custom CLI doctor command**
Explanation: ____________________

**S11 — Custom CLI benchmark run**
Explanation: ____________________

**S12 — JSON/CSV exports**
Explanation: ____________________

**S13 — Model comparison**
Explanation: ____________________

**S14 — Regression replay**
Explanation: ____________________

**S15 — pytest passing**
Explanation: ____________________

**S16 — GitHub repository structure**
Explanation: ____________________
