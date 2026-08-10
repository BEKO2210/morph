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

## Modes

- No flag: run, select winner, export patch/report, **do not alter base tree**.
- `--apply`: apply winner to base tree, leave uncommitted.
- `--commit`: apply + local commit.
- `--push`: apply + commit + push. This is the only mode that touches the remote.
- `--keep-worktrees`: debugging only; skip apoptosis cleanup.

MORPH requires a clean base working tree for apply/commit/push. That is deliberate: it avoids mixing a selected repair with unrelated local changes.

## Configuration

`morph.yaml` is JSON-formatted YAML so MORPH can parse it with the Python standard library and has zero Python dependencies.

Useful fields:

```json
{
  "clones": 3,
  "fitness_threshold": 0.45,
  "test_commands": ["npm test"],
  "predator_commands": ["npm run fuzz", "npm run test:integration"]
}
```

If `test_commands` is empty MORPH auto-detects common Node, Python, Go, Rust, Maven and Gradle checks.

## Claude Code adapter

MORPH invokes Claude Code in non-interactive print mode and disables session persistence. The Builder gets file read/edit tools; Predator and Guardian are read-only. MORPH itself executes project tests after the Builder finishes.

## Codex adapter

MORPH invokes `codex exec`. Builder runs under `workspace-write`; Predator/Guardian under `read-only`. Approval policy is non-interactive (`never`) so a one-shot run cannot hang waiting for an approval prompt.

## Output

Each run writes:

```text
.morph/runs/<run-id>/
├── sensing.json
├── candidate-1.json
├── candidate-1.patch
├── candidate-2.json
├── candidate-2.patch
├── candidate-3.json
├── candidate-3.patch
├── winner.patch
└── result.json
```

Persistent local learning:

```text
.morph/memory/
├── antibodies.json
└── pheromones.json
```

## Important scope of v0.1

This is an executable research-grade foundation, not a claim that every biological metaphor is already a learned model. The current stress field is a lightweight static graph, predictive CI is represented by risk-weighted verification hooks rather than a trained predictor, and clonal evolution currently occurs across causal hypotheses rather than repeated mutation generations. The architecture is intentionally modular so those can be upgraded without changing the one-shot CLI contract.
