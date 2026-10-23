# Garak — Day 4 evidence workflow (local Ollama)

Garak workflow: **Probe → Generator → Detector → Evaluator**. It is best for broad scanning
with built-in attack families.

| Term | Meaning |
|---|---|
| **Probe** | An attack / test family that produces input prompts (e.g. `encoding.InjectBase64`). |
| **Generator** | The interface to the target model — here `ollama.OllamaGeneratorChat`. |
| **Detector** | Checks each response for a specific failure condition. |
| **Evaluator** | Aggregates detector results into pass rates per probe/detector. |
| **Buff** | Transforms inputs (paraphrase, encoding) before they reach the generator. |
| **Generation** | One model output. `--generations 3` on a probe with 10 prompts ≈ 30 outputs. **Generations ≠ prompts.** |

## 1. Install (separate virtualenv)

```bash
cd ~/DAY_4
python3 -m venv .venv-garak
source .venv-garak/bin/activate
python -m pip install --upgrade pip
python -m pip install garak
```

`a4sec doctor --garak-python ~/DAY_4/.venv-garak/bin/python` records the Garak version.

## 2. Inventory before scanning (S07)

```bash
python -m garak --version
python -m garak --list_probes
python -m garak --list_detectors
python -m garak --list_generators
python -m garak --list_buffs
python -m garak --plugin_info probes.encoding.InjectBase64
```

Save the lists as evidence:

```bash
python -m garak --list_probes > ~/DAY_4/reports/garak/probes.txt
```

## 3. Scans (S08) — local models only

```bash
# Small baseline
python -m garak --target_type ollama.OllamaGeneratorChat --target_name llama3.2 \
  --spec probes.encoding.InjectBase64 --generations 1 --report_prefix day4_llama32_encoding

# Broader, both models (check exact probe names with --list_probes first)
python -m garak --target_type ollama.OllamaGeneratorChat --target_name llama3.2 \
  --spec probes.encoding.InjectBase64,probes.promptinject,probes.dan.Dan_11_0 \
  --generations 1 --report_prefix day4_llama32

python -m garak --target_type ollama.OllamaGeneratorChat --target_name qwen2.5:3b \
  --spec probes.encoding.InjectBase64,probes.promptinject,probes.dan.Dan_11_0 \
  --generations 1 --report_prefix day4_qwen25
```

Start with `--generations 1` on CPU/GPU-limited laptops.

### Relating Garak to the three A4 benchmark categories

Garak has no probe for the instructor's exact rubric. Use `--list_probes` to find built-in
families that request harmful/illegal-substance content or try to bypass refusals
(probe names change between versions — candidates to look for include a `grandma` *Substances*
probe, `donotanswer`, and the `dan` jailbreak family) and run them on both models. Report them as
**related** evidence; the rubric itself (≥ 70 % threshold) is applied by `a4sec` and by
`promptfoo/benchmarks.promptfooconfig.yaml`.

## 4. Where the evidence is (S09)

```bash
find ~/.local/share/garak/garak_runs/ -maxdepth 1 -type f -name 'day4_*' -print
xdg-open <the .report.html path printed by garak>
```

Each run writes a `*.report.jsonl` (every attempt: prompt, outputs, detector scores), a
`*.hitlog.jsonl` (detector hits) and a `*.report.html` (aggregate). Copy them to
`~/DAY_4/reports/garak/` for submission — they are git-ignored here.

## 5. Reading results correctly

| Item | Meaning | Never claim |
|---|---|---|
| Probe pass rate | Fraction that passed that probe's detector | "The model is X % secure." |
| Hit / detector output | A *possible* failure in one response | "Every hit is a confirmed exploit." |
| DEFCON grade | Relative grade calibrated against reference runs | "The grade alone proves a vulnerability." |
| JSONL response | Input/output detail for review | "The LLM response proves tool side effects." |

Open the JSONL, read the actual responses behind a hit, and repeat a surprising one before calling it a finding.
