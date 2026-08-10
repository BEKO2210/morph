# MORPH — Morphogenetic Autonomous Repair Fabric

**Code that heals before it breaks.**

MORPH is a one-shot multi-agent coding harness. It does not stay resident and it does not run a daemon. One invocation performs a complete lifecycle and exits.

## What one run does

1. **Repository sensing / homeostasis baseline** — captures Git state, dependency/public-surface signals, and available verification commands.
2. **Stress field** — builds a lightweight import graph and propagates attention from task-relevant files.
3. **Counterfactual clonal repair** — creates isolated `git worktree` clones with materially different causal hypotheses.
4. **BUILDER** — each clone implements the task independently.
5. **PREDATOR** — read-only adversarial review attempts to falsify each candidate.
6. **GUARDIAN** — read-only review protects minimality, compatibility, dependencies, and repository homeostasis.
7. **Execution** — MORPH runs detected tests/lint/typecheck/build commands plus optional configured predator commands.
8. **Fitness selection** — combines execution, adversarial review, homeostasis, minimality, blast radius and dependency stability.
9. **Apoptosis / cleanup** — temporary worktrees and branches are deleted.
10. **Immune memory / pheromones** — only abstract diagnosis/verification signals and decaying file-risk traces persist under `.morph/memory/`.
11. **Exit** — the process ends. No background service remains.

## Start in one command

After extracting this folder into the root of a target Git repository:

```bash
bash morph_system/install.sh && ./morph-once --adapter claude --apply "Implementiere Feature X und behebe alle Regressionen"
```

With Codex:

```bash
bash morph_system/install.sh && ./morph-once --adapter codex --apply "Implement feature X"
```

Or auto-detect:

```bash
bash morph_system/install.sh && ./morph-once --adapter auto --apply "Implement feature X"
```

Check the local prerequisites after installation:

```bash
./morph-once doctor
```

Run MORPH's packaged regression tests:

```bash
bash morph_system/run-tests.sh
```

## Modes

- No flag: run, select winner, export patch/report, **do not alter base tree**.
- `--apply`: apply winner to base tree, leave uncommitted.
- `--commit`: apply + local commit.
- `--push`: apply + commit + push. This is the only mode that touches the remote.
- `--keep-worktrees`: debugging only; skip apoptosis cleanup.
- `--verbose` / `-v`: also echo raw agent/check output live on stderr, not just `[MORPH] ...` progress lines.

A candidate is never applied when an executed verification command fails (unless `require_all_checks_pass` is explicitly disabled). Predator and Guardian severity also act as hard selection gates in addition to the weighted fitness score.

MORPH requires a clean base working tree for apply/commit/push. That is deliberate: it avoids mixing a selected repair with unrelated local changes.

## Progress and logs

Every run prints `[MORPH] ...` progress lines (sensing, hypothesis generation, Builder start/done with duration and changed-file count, each check command, Predator/Guardian start/done, cleanup) to **stderr** and appends them to `run_dir/progress.log`, so a run is never silently stuck for minutes. **stdout carries only the final JSON result** — safe to pipe into `jq` or any script. Pass `--verbose`/`-v` to additionally echo raw agent/check stdout+stderr live (also on stderr); it is always teed to per-candidate `.builder.log` / `.predator.log` / `.guardian.log` files regardless of `--verbose`.

## Resilience

- **Transient network errors** (dropped websocket, connection reset, HTTP 5xx) during a Builder/Predator/Guardian call are retried with exponential backoff — `agent_max_retries` (default 2) and `agent_retry_backoff_s` (default 5.0) in `morph.yaml`. Normal agent/task failures (a bad prompt, a real bug) are never retried.
- If a Predator/Guardian review still fails after retries are exhausted, that **candidate** is degraded (scored at maximum severity with a traceable finding) instead of the whole run crashing.
- If the Builder produces an empty diff, the candidate is journaled with an explicit `"status": "builder-no-change"` and excluded from review and fitness-based selection — it is never silently scored like a normal candidate.
- Each candidate's JSON is journaled atomically after every phase (worktree creation, Builder, each check, each review), so a mid-run crash preserves whatever work already completed instead of losing the candidate entirely.
- `result.json` (with `status: "run-failed"`) and `error.json` (with the exception type, message, and traceback) are written on **every** controlled exit path, including an unexpected exception anywhere in the run, before apoptosis cleanup runs in a `finally` block.

## Configuration

`morph.yaml` is JSON-formatted YAML so MORPH can parse it with the Python standard library and has zero Python dependencies.

Useful fields:

```json
{
  "clones": 3,
  "fitness_threshold": 0.45,
  "require_all_checks_pass": true,
  "max_predator_severity": 0.65,
  "max_guardian_severity": 0.65,
  "agent_max_retries": 2,
  "agent_retry_backoff_s": 5.0,
  "progress_heartbeat_s": 20,
  "test_commands": ["npm test"],
  "predator_commands": ["npm run fuzz", "npm run test:integration"]
}
```

If `test_commands` is empty MORPH auto-detects common Node, Python, Go, Rust, Maven and Gradle checks.

## Claude Code adapter

MORPH invokes Claude Code in non-interactive print mode and disables session persistence. The Builder gets file read/edit tools; Predator and Guardian are read-only. MORPH itself executes project tests after the Builder finishes.

## Codex adapter

MORPH invokes `codex --ask-for-approval never exec --ephemeral --sandbox <mode>`. `--ask-for-approval` is a **global** codex option and must precede the `exec` subcommand (codex ≥ 0.147 rejects `codex exec --ask-for-approval ...` with `unexpected argument '--ask-for-approval' found`). Builder runs under `workspace-write`; Predator/Guardian under `read-only`. `--ephemeral` keeps the run one-shot with no persisted session.

## Output

Each run writes, updated atomically as each phase completes (not only at the end):

```text
.morph/runs/<run-id>/
├── sensing.json
├── progress.log
├── hypotheses.log
├── g0-candidate-1.json
├── g0-candidate-1.patch
├── g0-candidate-1.builder.log
├── g0-candidate-1.checks.json
├── g0-candidate-1.predator.log
├── g0-candidate-1.guardian.log
├── ... (g0-candidate-2, g0-candidate-3, g1-candidate-*, ...)
├── winner.patch
├── result.json
└── error.json   # only present if the run hit an unexpected exception
```

Persistent local learning:

```text
.morph/memory/
├── antibodies.json
└── pheromones.json
```

## Important scope of v0.1

This is an executable research-grade foundation, not a claim that every biological metaphor is already a learned model. The current stress field is a lightweight static graph, predictive CI is represented by risk-weighted verification hooks rather than a trained predictor, and clonal evolution currently uses one configurable mutation generation after the causal seed population rather than an unbounded evolutionary loop. The architecture is intentionally modular so those can be upgraded without changing the one-shot CLI contract.
