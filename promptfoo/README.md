# Promptfoo — Day 4 evidence workflow (local Ollama)

Promptfoo workflow: **Test cases → Provider → Response → Score**. It is best for
student-defined assertions and regression checks. All targets and graders here are
`ollama:chat:*`; nothing is sent to a cloud model.

## 0. Workspace and class files

```bash
mkdir -p ~/DAY_4/reports/promptfoo ~/DAY_4/reports/garak
cd ~/DAY_4
# Download the two companion files from the class folder and save them as
#   promptfooconfig.yaml   (T01–T06 BankBot deterministic tests)
#   redteam_config.yaml    (red-team plugins/strategies)
# https://drive.google.com/drive/folders/1hf9GD_v_GIPzhYVc6scBr3n0IPQPzTrr?usp=sharing
ls -lah
```

The class files are not copied into this repository; keep the originals with your evidence.

## 1. Keep everything local

```bash
export OLLAMA_BASE_URL=http://127.0.0.1:11434
export PROMPTFOO_DISABLE_REMOTE_GENERATION=true
export PROMPTFOO_DISABLE_REDTEAM_REMOTE_GENERATION=true
export PROMPTFOO_DISABLE_TELEMETRY=1
export PROMPTFOO_DISABLE_SHARING=1
export PROMPTFOO_DISABLE_UPDATE=1
```

Environment variables alone do not guarantee offline isolation — the companion configs also set
the target and grader explicitly to Ollama. Block egress if your policy requires it.

## 2. Version, help, validation

```bash
promptfoo --version            # S01
promptfoo --help
promptfoo validate -c promptfooconfig.yaml      # S03
promptfoo validate -c redteam_config.yaml
```

## 3. Deterministic evaluation (T01–T06 × 5)

```bash
promptfoo eval -c promptfooconfig.yaml \
  --repeat 5 --no-cache --no-share -j 1 \
  --output reports/promptfoo/bankbot.html \
  --output reports/promptfoo/bankbot.json \
  --output reports/promptfoo/bankbot.csv
xdg-open reports/promptfoo/bankbot.html          # S04
```

Six cases × five repetitions = up to **30** target outputs (fewer if errors/skips). For each FAIL,
capture the input, the response, the assertion reason and the model/version. T04 (French
translation) needs manual review — a literal check cannot catch translated or spelled-out leakage.

Deterministic testing is useful for: functionality assertions, known security regression checks,
scope checks, and reproducible repeated evaluation.

## 4. Red-team generation → inspection → evaluation

```bash
promptfoo redteam generate -c redteam_config.yaml -o redteam.yaml --no-cache -j 1 --strict
grep -n 'tests:' redteam.yaml        # confirm generated tests exist   (S05)
nano redteam.yaml                    # inspect a subset of generated inputs

promptfoo redteam eval -c redteam.yaml --no-cache --no-share -j 1 \
  --output reports/promptfoo/redteam.html \
  --output reports/promptfoo/redteam.json \
  --output reports/promptfoo/redteam.csv
promptfoo redteam report             # S06
```

One-command alternative (less inspectable):
`promptfoo redteam run -c redteam_config.yaml -o redteam.yaml -j 1 --no-cache --strict`

> **False 100 % PASS pitfall.** `promptfoo eval -c redteam_config.yaml --repeat 5` without generated
> `tests:` can return five generic PASS results. That only proves inference worked, not robustness.
> Always confirm `tests:` exists and read some generated cases before reporting numbers.

On a laptop start with the `basic` and `base64` strategies, then add `rot13`, `hex`, `leetspeak`.

## 5. The three A4 benchmark categories in Promptfoo

`benchmarks.promptfooconfig.yaml` runs the instructor benchmark prompts on both models and grades
them with `assertions/rubric_score.js`, which implements the same weighted/gated rubric as `a4sec`
(score ≥ threshold → FAIL; mentions in refusal/safety sentences not credited).

```bash
cd promptfoo
cp benchmarks.local.yaml.example benchmarks.local.yaml   # git-ignored; fill from course materials
promptfoo validate -c benchmarks.promptfooconfig.yaml
promptfoo eval -c benchmarks.promptfooconfig.yaml --repeat 5 --no-cache --no-share -j 1 \
  --output ../reports/promptfoo/benchmarks.html \
  --output ../reports/promptfoo/benchmarks.json \
  --output ../reports/promptfoo/benchmarks.csv
```

The HTML/JSON outputs of this run contain full model responses — keep them local and share them
only through the instructor channel, not GitHub.

## 6. Evidence to keep

| Item | Where |
|---|---|
| Command used | screenshot + `reports/evidence/commands.txt` |
| Configuration file | `promptfooconfig.yaml`, `redteam_config.yaml`, `benchmarks.promptfooconfig.yaml` |
| Generated tests | `redteam.yaml` |
| Model / provider | provider IDs in configs; `ollama list` output |
| Repeated outputs | JSON/CSV reports (`--repeat 5`) |
| Pass/fail assertion reason | HTML report → open a FAIL |
| HTML / JSON / CSV reports | `reports/promptfoo/` |

Never state that a 100 % PASS proves the model is secure.
