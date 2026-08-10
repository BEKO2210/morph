from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable

from ..util import filter_ignored_status, run_cmd


@dataclass
class HomeostasisVector:
    git_clean: float
    tracked_files: int
    changed_files: int
    diff_lines: int
    dependency_files_changed: int
    public_surface_files_changed: int

    def to_dict(self) -> dict:
        return asdict(self)


def _changed_files(repo: Path, base: str | None = None) -> list[str]:
    args = ["git", "diff", "--name-only"]
    if base:
        args.append(base)
    out = run_cmd(args, cwd=repo).stdout
    return [line.strip() for line in out.splitlines() if line.strip()]


def _diff_lines(repo: Path, base: str | None = None) -> int:
    args = ["git", "diff", "--numstat"]
    if base:
        args.append(base)
    out = run_cmd(args, cwd=repo).stdout
    total = 0
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2:
            for x in parts[:2]:
                if x.isdigit():
                    total += int(x)
    return total


def sense(repo: Path, base: str | None = None, ignore_paths: Iterable[str] = ()) -> HomeostasisVector:
    status = run_cmd(["git", "status", "--porcelain"], cwd=repo).stdout
    # git diff --name-only only ever reports tracked-file changes, but
    # `git status --porcelain` also lists untracked files — including
    # MORPH's own install artifacts (.morph/, morph.yaml, ...) when they
    # haven't been committed to the target repo. Filter those out the same
    # way the apply-safety check does, so MORPH never mistakes its own
    # untracked files for a dirty project working tree.
    dirty = filter_ignored_status(status, ignore_paths)
    tracked = run_cmd(["git", "ls-files"], cwd=repo).stdout.splitlines()
    changed = _changed_files(repo, base)
    dep_names = {
        "package.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock",
        "pyproject.toml", "poetry.lock", "requirements.txt", "uv.lock",
        "go.mod", "go.sum", "Cargo.toml", "Cargo.lock", "pom.xml", "build.gradle",
    }
    dep_changed = sum(Path(p).name in dep_names for p in changed)
    surface_tokens = ("api", "routes", "router", "schema", "migration", "public", "export", "types")
    surface = sum(any(tok in p.lower() for tok in surface_tokens) for p in changed)
    return HomeostasisVector(
        git_clean=1.0 if not dirty else 0.0,
        tracked_files=len(tracked),
        changed_files=len(changed),
        diff_lines=_diff_lines(repo, base),
        dependency_files_changed=dep_changed,
        public_surface_files_changed=surface,
    )
