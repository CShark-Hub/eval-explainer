# eval-explainer

A local, CSHARK-styled viewer for `claude plugin eval --json` results. Point it at
a folder of result files, or drop them on the page, and it shows whether a skill
beats its no-skill baseline, and why.

- **Hero:** model, judge, ablation and Claude Code version. KPI tiles for the score
  difference between the arms, each arm's mean score, runs, total cost and wall
  clock.
- **01 Arm comparison:** paired bars for score, full pass, deterministic pass, judge
  PASS, skill fired, cost, time and turns.
- **02 Per case:** baseline vs skill score for every case, sorted by the gap, with
  case tags. Click a case to drill in.
- **03 Grader matrix:** pass rate per case and grader, toggled between skill,
  baseline and the difference.
- **04 Case detail:** every run, with grader verdicts (hover for the explanation),
  judge votes, the answer and the prompt.

Scores leave out the `skill-fired` grader, so both arms sit on one scale even
under `--ablation none`, where that grader is scored.

## Run it

Python 3 only, no dependencies:

```bash
python3 serve.py --open                                   # the bundled examples
python3 serve.py --results path/to/results --cases path/to/evals/cases --open
```

Or Docker:

```bash
docker compose up --build -d                              # examples, http://127.0.0.1:8077
RESULTS_DIR=/abs/path/results CASES_DIR=/abs/path/evals/cases docker compose up -d
PORT=9000 docker compose up -d                            # another host port
docker compose down
```

Either way it listens on `127.0.0.1` only. Result folders are mounted read-only.
New files show up after a page reload, with no rebuild.

Without a server, open `index.html` straight from disk and drop files on it.

## Drag and drop

Drop any number of result JSON files anywhere on the page, use **Open JSON…**, or
open the optional **Dropzone** panel. Each file becomes its own source under
"Dropped" in the dropdown, and the page shows one source at a time. Files that are
not eval results are listed with the reason and skipped. Dropped files stay in the
browser tab and are never uploaded.

## Inputs

- `*.json`: output of `claude plugin eval … --json OUT.json`. A file whose name ends
  in `-baseline.json` labels its single arm "baseline". With several files, a
  `-both.json` (with-without ablation) file opens first.
- Case tags (optional) come from `tags.json` in the results folder
  (`{"case-name": ["happy"]}`), and from the `tags:` line of each
  `<case>/prompt.md` when you pass `--cases`.

## Examples

`examples/` holds two real runs of a `commit-message` skill: 15 cases, 3 runs per
arm, model `haiku`, judge `claude-sonnet-5-5`.

- `20261011-222149-both.json`: skill vs no-skill baseline (`--ablation with-without`).
- `20261011-222450-skill.json`: skill arm only (`--ablation none`).
- `tags.json`: the happy / edge / adversarial tags of those cases.

The prompts contain upstream patches from `vitejs/vite` and
`conventional-changelog/commitlint` (MIT).

## Files

```
index.html     the whole app: one page, inline CSS and JS
serve.py       stdlib HTTP server: lists results, serves the page
Dockerfile     python:3.12-slim, runs as nobody
compose.yaml   localhost-only port, read-only result mounts
examples/      sample results and tags
```
