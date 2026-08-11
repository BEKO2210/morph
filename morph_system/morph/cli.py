from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .config import load_config
from .colony.orchestrator import run_once


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="morph", description="MORPH — one-shot morphogenetic autonomous repair fabric")
    sub = p.add_subparsers(dest="cmd", required=True)
    # The morph-once wrapper injects the subcommand, so its --help must not
    # advertise "usage: morph run ..." — that invites users to type a "run"
    # the wrapper already supplied.
    run_prog = os.environ.get("MORPH_PROG")
    run = sub.add_parser("run", help="run one MORPH lifecycle and exit",
                         **({"prog": run_prog} if run_prog else {}))
    run.add_argument("task", help="coding task or repair goal")
    run.add_argument("--repo", default=".", help="target git repository")
    run.add_argument("--adapter", choices=["auto", "claude", "codex", "mock"], default="auto")
    run.add_argument("--apply", action="store_true", help="apply the winning patch to the base working tree (uncommitted)")
    run.add_argument("--commit", action="store_true", help="apply and commit the winning patch")
    run.add_argument("--push", action="store_true", help="apply, commit and push the winning patch")
    run.add_argument("--keep-worktrees", action="store_true", help="debug: keep temporary clone worktrees")
    run.add_argument("--verbose", "-v", action="store_true", help="also echo raw agent/check output live, not just [MORPH] progress lines")
    run.add_argument("--clones", type=int, metavar="N", help="override morph.yaml: number of causally-diverse first-generation clones (default 3)")
    run.add_argument("--evolution", type=int, metavar="N", dest="clone_evolution", help="override morph.yaml: number of clonal-evolution rounds after generation 0 (0 disables evolution, default 1)")
    run.add_argument("--evolution-children", type=int, metavar="N", help="override morph.yaml: mutation-pressure children per evolution round (default 3)")
    doctor = sub.add_parser("doctor", help="check prerequisites")
    doctor.add_argument("--repo", default=".")
    doctor.add_argument("--json", action="store_true", help="machine-readable output for scripts/CI (default: human-readable)")
    return p


def doctor(repo: Path, as_json: bool = False) -> int:
    from .util import which, run_cmd
    is_repo = run_cmd(["git", "rev-parse", "--is-inside-work-tree"], cwd=repo).returncode == 0
    data = {
        "python": sys.version.split()[0],
        "git": which("git"),
        "claude": which("claude"),
        "codex": which("codex"),
        "is_git_repo": is_repo,
    }
    ready = bool(data["git"]) and is_repo and (bool(data["claude"]) or bool(data["codex"]))

    if as_json:
        print(json.dumps(data, indent=2))
        return 0 if ready else 2

    def line(label: str, value, hint: str = "") -> None:
        mark = "OK " if value else "!! "
        shown = value if isinstance(value, str) else ("yes" if value else "no")
        print(f"  [{mark}] {label}: {shown}")
        if not value and hint:
            print(f"        -> {hint}")

    print("MORPH doctor — checking what's needed to run a real one-shot cycle\n")
    line("Python", data["python"])
    line("git", data["git"], "Install git for your OS, e.g. 'sudo apt install git' (Debian/Ubuntu) or 'brew install git' (macOS).")
    line("Inside a git repository", data["is_git_repo"], "Run this from inside your project's git repo, or pass --repo <path>.")
    line("Claude Code (claude)", data["claude"], "npm install -g @anthropic-ai/claude-code -- then run: claude login")
    line("Codex (codex)", data["codex"], "npm install -g @openai/codex -- then run: codex login")
    print()
    if not data["claude"] and not data["codex"]:
        print("Neither Claude Code nor Codex is installed. Install at least one of the two commands above,")
        print("or run with --adapter mock to dry-run MORPH's own pipeline without a real coding agent.")
    elif ready:
        print("Ready. Try:")
        print('  ./morph-once --adapter auto --apply "describe the bug or feature you want fixed"')
    else:
        print("Not ready yet — fix the [!!] items above, then run './morph-once doctor' again.")
    return 0 if ready else 2


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    repo = Path(args.repo).resolve()
    if args.cmd == "doctor":
        return doctor(repo, as_json=args.json)
    cfg = load_config(repo)
    # CLI flags win over morph.yaml when given, so you never have to
    # hand-edit JSON just to try a different clone/evolution count.
    if args.clones is not None:
        cfg.clones = args.clones
    if args.clone_evolution is not None:
        cfg.clone_evolution = args.clone_evolution
    if args.evolution_children is not None:
        cfg.evolution_children = args.evolution_children
    try:
        result = run_once(
            repo, args.task, args.adapter, cfg,
            apply=args.apply or args.commit or args.push,
            commit=args.commit or args.push,
            push=args.push,
            keep_worktrees=args.keep_worktrees,
            verbose=args.verbose,
        )
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0 if result["status"] == "winner-selected" else 3
    except KeyboardInterrupt:
        print("MORPH interrupted; cleanup attempted.", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"MORPH ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
