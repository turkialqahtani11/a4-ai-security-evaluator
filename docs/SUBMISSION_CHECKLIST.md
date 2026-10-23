# A4 Submission Checklist

**Deadline: Tuesday, 27 October 2026 — 12:00 AM (Riyadh).**
"12:00 AM Tuesday" is the midnight between Monday 26 and Tuesday 27 October — plan to submit on
**Monday 26 October** to be safe. Certificates for eligible participants are planned for
Wednesday, 28 October 2026.

## 1. Promptfoo / Garak evidence

- [ ] Screenshots S01–S09 (see `SCREENSHOT_CHECKLIST.md`), each with a one-sentence explanation
- [ ] Promptfoo original local reports: `bankbot.{html,json,csv}`, `redteam.yaml`, `redteam.{html,json,csv}`
- [ ] Promptfoo benchmark reports (`benchmarks.*`) — shared privately, not on GitHub
- [ ] Garak `*.report.html`, `*.report.jsonl`, `*.hitlog.jsonl` for llama3.2 and qwen2.5:3b

## 2. GitHub repository

- [ ] Runnable Python CLI (`a4sec doctor | run | compare | replay | summarize`)
- [ ] README
- [ ] Automated tests (`pytest -q` passes)
- [ ] Sample JSON (`samples/sample_results.json`)
- [ ] Sample CSV (`samples/sample_results.csv`)
- [ ] `configs/*.local.yaml`, `promptfoo/benchmarks.local.yaml` and `reports/` are **not** committed (`git status` clean of them)

## 3. Short PDF findings summary

Built from `docs/REPORT_TEMPLATE.md`. Must cover:

- [ ] Environment
- [ ] Methodology
- [ ] Results
- [ ] Finding(s)
- [ ] Impact
- [ ] Root cause
- [ ] Mitigation
- [ ] Limitations
- [ ] Reproducibility

## 4. Demonstration video

- [ ] Runs the tool
- [ ] Explains the implementation
- [ ] Shows evidence/output
- [ ] Explains meaningful code/comments

## 5. Submission form

<https://docs.google.com/forms/d/e/1FAIpQLScHBx5tE2VHmFmpifY2zYdUaAqwW5XFDy5ST9roL7Qn_1vxNA/viewform>

- [ ] Select **A4**
- [ ] GitHub link
- [ ] Google Drive PDF link
- [ ] Google Drive video link
- [ ] Evidence folder link (screenshots + reports)

## Final checks

- [ ] GitHub link opens correctly (public, or instructors added)
- [ ] Google Drive PDF is viewable by instructors
- [ ] Google Drive video is viewable by instructors
- [ ] Reports/screenshots are complete
- [ ] No fake or unverified results (samples are labelled as mocked)
- [ ] No private credentials
- [ ] No unsafe procedural content published (repo, PDF, video, screenshots)
