<div align="center">

<img src="assets/banner.svg" alt="MORPH — One-Shot Multi-Agent Repair Fabric" width="100%" />

<br/>

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](morph_system/LICENSE)
[![Version](https://img.shields.io/badge/version-0.1.0-informational.svg)](morph_system/VERSION)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue.svg)](#requirements)
[![Architecture](https://img.shields.io/badge/architecture-one--shot%2C%20no%20daemon-success.svg)](#what-a-run-actually-does)
[![Dependencies](https://img.shields.io/badge/python%20deps-zero-success.svg)](#requirements)

**Code that heals before it breaks.**

</div>

---

MORPH is a one-shot, multi-agent coding harness for Claude Code and Codex. It does **not** run as a background service. A single invocation runs one full evolutionary lifecycle — sense the repo, grow independent repair candidates in isolated git worktrees, battle-test them, select a winner by executable evidence, and exit.

## Table of contents

- [Quick start](#quick-start)
- [What a run actually does](#what-a-run-actually-does)
- [CLI modes](#cli-modes)
- [Configuration](#configuration)
- [Adapters](#adapters)
- [Run artifacts](#run-artifacts)
- [Repository layout](#repository-layout)
- [Security model](#security-model)
- [Verifying this release](#verifying-this-release)
- [Scope of v0.1](#scope-of-v01)
- [License](#license)

## Quick start

Extract this repository's contents into the root of the target git repo (already done here), then:

```bash
bash morph_system/install.sh && ./morph-once --adapter claude --apply "YOUR TASK HERE"
```

Codex instead of Claude Code:

```bash
bash morph_system/install.sh && ./morph-once --adapter codex --apply "YOUR TASK HERE"
```

Auto-detect Claude Code, falling back to Codex:

```bash
bash morph_system/install.sh && ./morph-once --adapter auto --apply "YOUR TASK HERE"
```

Claude Code is driven through its non-interactive `claude -p` print mode; Codex is driven through `codex exec` with `workspace-write` / `read-only` sandboxing. See [`morph_system/README.md`](morph_system/README.md) for the full adapter reference.

## What a run actually does

```mermaid
flowchart TD
    A["Task"] --> B["Repository Sensing"]
    B --> C["Homeostasis + Stress Field"]
    C --> D{"3 causally distinct clones"}
    D --> E1["Clone A · Builder → Tests → Predator → Guardian"]
    D --> E2["Clone B · Builder → Tests → Predator → Guardian"]
    D --> E3["Clone C · Builder → Tests → Predator → Guardian"]
    E1 --> F["Fitness Selection"]
    E2 --> F
    E3 --> F
    F --> G["Strongest clone reproduces:<br/>minimalize · harden · simplify"]
    G --> H["Battle + tests again"]
    H --> I["6 repository states scored"]
    I --> J(("WINNER"))
    J --> K["winner.patch"]
    J --> L["Immune Memory"]
    J --> M["Pheromone Map"]
    J --> N["Hysteretic Trust"]
    K --> O["Apoptosis: delete temp worktrees"]
    L --> O
    M --> O
    N --> O
    O --> P["Exit"]
```

Every run is a single pass through this graph — no daemon, no persistent process, nothing left running after `EXIT`.

## CLI modes

| Flag | Effect |
|---|---|
| *(none)* | Run, select a winner, write patch + report. **Base working tree is never touched.** |
| `--apply` | Apply the winner to the base tree, leave it uncommitted. Recommended for getting started. |
| `--commit` | Apply + local commit. |
| `--push` | Apply + commit + push. The only mode that touches the remote. |
| `--keep-worktrees` | Debug only — skips apoptosis cleanup. |

MORPH refuses to apply/commit/push onto a dirty base working tree, so a selected repair is never mixed with unrelated local changes.

## Configuration

`morph.yaml` (generated at the repo root by `install.sh`) is JSON-formatted YAML, parsed with the Python standard library only:

```json
{
  "clones": 3,
  "fitness_threshold": 0.45,
  "test_commands": ["npm test"],
  "predator_commands": ["npm run fuzz", "npm run test:integration"]
}
```

If `test_commands` is left empty, MORPH auto-detects common Node, Python, Go, Rust, Maven, and Gradle checks. Fitness weighs execution results, adversarial (Predator) review, Guardian review, minimality, blast radius, dependency stability, and task signal — see `homeostasis` in `morph.yaml` to tune the balance.

## Adapters

| Adapter | Backing CLI | Builder sandbox | Predator / Guardian |
|---|---|---|---|
| `claude` | `claude -p` (non-interactive, no session persistence) | file read/edit tools only | read-only |
| `codex` | `codex exec` | `workspace-write` | `read-only`, non-interactive approval |
| `mock` | none (built-in) | in-process | in-process — used for smoke-testing MORPH itself |
| `auto` | detects `claude`, then falls back to `codex` | — | — |

## Run artifacts

Each invocation writes a complete, inspectable trail:

```text
.morph/runs/<run-id>/
├── sensing.json
├── g0-candidate-1.json / .patch
├── g0-candidate-2.json / .patch
├── g0-candidate-3.json / .patch
├── g1-candidate-1.json / .patch
├── g1-candidate-2.json / .patch
├── g1-candidate-3.json / .patch
├── winner.patch
└── result.json

.morph/memory/
├── antibodies.json   # immune memory
├── pheromones.json   # decaying file-risk traces
└── trust.json        # hysteretic trust
```

Both directories are gitignored by default (see `.gitignore`).

## Repository layout

```text
.
├── README.md              ← you are here
├── START-MORPH.txt        ← copy-paste quick start
├── CHECKSUMS.txt          ← SHA-256 manifest for this release
├── morph.yaml             ← per-repo config, generated by install.sh
├── morph-once             ← generated CLI wrapper, generated by install.sh
└── morph_system/          ← vendored MORPH package
    ├── README.md          ← full reference documentation
    ├── ARCHITECTURE.md    ← design invariant + ASCII pipeline diagram
    ├── SECURITY.md        ← security model
    ├── LICENSE            ← MIT
    ├── VERSION
    ├── install.sh / doctor.sh / run-once.sh
    ├── morph/             ← implementation (adapters, colony, core, ci, git, memory)
    └── tests/             ← pytest smoke + unit tests
```

## Security model

- Temporary repair candidates live in isolated `git worktree` clones, force-cleaned in a `finally` path.
- The Claude Builder gets scoped file tools (`Read`/`Edit`/`Write`/`Glob`/`Grep`), never unrestricted shell access; Predator and Guardian are read-only.
- The Codex Builder runs under `workspace-write`; reviews run under `read-only` with non-interactive approval.
- MORPH itself only executes verification commands it auto-detected from project manifests or that you explicitly configured in `morph.yaml`.
- Nothing is pushed unless you pass `--push`.
- Apply/commit/push all refuse to run against a dirty base tree.

Full details in [`morph_system/SECURITY.md`](morph_system/SECURITY.md). Treat any repository's test/build scripts as executable code — review third-party repositories before running an autonomous coding agent against them.

## Verifying this release

```bash
sha256sum -c CHECKSUMS.txt
```

Release checksum: `ff1ba5ac82b6cb25cc4de26c523fff5d5011b8e0bf52f0d1895e2390bb6fae7d`

## Scope of v0.1

This is an executable research-grade foundation, not a claim that every biological metaphor is already a learned model. The stress field is a lightweight static import graph, predictive CI is represented by risk-weighted verification hooks rather than a trained predictor, and clonal evolution currently spans causal hypotheses rather than repeated mutation generations. The architecture is intentionally modular so each of these can be upgraded later without changing the one-shot CLI contract.

## License

MIT — see [`morph_system/LICENSE`](morph_system/LICENSE).

<div align="center">
<sub><img src="assets/logo-mark.svg" width="20" height="20" align="absmiddle" alt="" /> Built for one-shot, evidence-based repair — not another background agent.</sub>
</div>
