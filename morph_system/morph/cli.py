from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import load_config
from .colony.orchestrator import run_once


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="morph", description="MORPH — one-shot morphogenetic autonomous repair fabric")
    sub = p.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run", help="run one MORPH lifecycle and exit")
    run.add_argument("task", help="coding task or repair goal")
    run.add_argument("--repo", default=".", help="target git repository")
    run.add_argument("--adapter", choices=["auto", "claude", "codex", "mock"], default="auto")
    run.add_argument("--apply", action="store_true", help="apply the winning patch to the base working tree (uncommitted)")
    run.add_argument("--commit", action="store_true", help="apply and commit the winning patch")
    run.add_argument("--push", action="store_true", help="apply, commit and push the winning patch")
    run.add_argument("--keep-worktrees", action="store_true", help="debug: keep temporary clone worktrees")
    doctor = sub.add_parser("doctor", help="check prerequisites")
    doctor.add_argument("--repo", default=".")
    return p


def doctor(repo: Path) -> int:
    from .util import which, run_cmd
    data = {
        "python": sys.version.split()[0],
        "git": which("git"),
        "claude": which("claude"),
        "codex": which("codex"),
        "is_git_repo": run_cmd(["git", "rev-parse", "--is-inside-work-tree"], cwd=repo).returncode == 0,
    }
    print(json.dumps(data, indent=2))
    return 0 if data["git"] and data["is_git_repo"] and (data["claude"] or data["codex"]) else 2


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    repo = Path(args.repo).resolve()
    if args.cmd == "doctor":
        return doctor(repo)
    cfg = load_config(repo)
    try:
        result = run_once(
            repo, args.task, args.adapter, cfg,
            apply=args.apply or args.commit or args.push,
            commit=args.commit or args.push,
            push=args.push,
            keep_worktrees=args.keep_worktrees,
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
