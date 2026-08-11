from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..util import run_cmd, slug


@dataclass
class Worktree:
    name: str
    path: Path
    branch: str
    base: str


class WorktreeManager:
    def __init__(self, repo: Path, run_id: str):
        self.repo = repo
        self.run_id = run_id
        self.root = repo / ".morph-worktrees" / run_id
        self.created: list[Worktree] = []

    def create(self, name: str, base: str) -> Worktree:
        safe = slug(name, 24)
        path = self.root / safe
        branch = f"morph/{self.run_id}/{safe}"
        path.parent.mkdir(parents=True, exist_ok=True)
        run_cmd(["git", "worktree", "add", "-q", "-b", branch, str(path), base], cwd=self.repo, check=True)
        wt = Worktree(safe, path, branch, base)
        self.created.append(wt)
        self._inherit_dependency_dirs(wt)
        return wt

    def _inherit_dependency_dirs(self, wt: Worktree) -> None:
        # `git worktree add` only ever checks out tracked files. Dependency
        # directories (node_modules, .venv, ...) are gitignored, so a fresh
        # worktree starts without them — any check command that needs them
        # (npm run lint/build, pytest against an installed venv, ...) would
        # fail with "command not found" regardless of how correct the
        # candidate's patch is. Symlink them in from the base repo instead
        # of reinstalling per candidate: fast, and dependencies aren't
        # expected to change within a single MORPH run.
        for dirname in ("node_modules", ".venv", "venv"):
            src = self.repo / dirname
            dst = wt.path / dirname
            if src.is_dir() and not dst.exists():
                try:
                    dst.symlink_to(src, target_is_directory=True)
                except OSError:
                    pass

    def _intent_to_add_untracked(self, wt: Worktree) -> None:
        # Make untracked Builder output visible to `git diff` without committing it.
        # Dependency directories inherited by MORPH are symlinks, so ignore
        # patterns ending in "/" do not match them as directories. Explicit
        # negative pathspecs keep MORPH's own scaffolding out of candidate
        # patches while still exposing every Builder-created file.
        run_cmd([
            "git", "add", "-N", "--", ".",
            ":(exclude)node_modules", ":(exclude).venv", ":(exclude)venv",
        ], cwd=wt.path)

    def patch(self, wt: Worktree) -> str:
        self._intent_to_add_untracked(wt)
        return run_cmd(["git", "diff", "--binary", wt.base, "--"], cwd=wt.path).stdout

    def changed_files(self, wt: Worktree) -> list[str]:
        self._intent_to_add_untracked(wt)
        out = run_cmd(["git", "diff", "--name-only", wt.base, "--"], cwd=wt.path).stdout
        return [x for x in out.splitlines() if x.strip()]

    def cleanup_one(self, wt: Worktree) -> None:
        run_cmd(["git", "worktree", "remove", "--force", str(wt.path)], cwd=self.repo)
        run_cmd(["git", "branch", "-D", wt.branch], cwd=self.repo)

    def cleanup_all(self) -> None:
        for wt in reversed(self.created):
            self.cleanup_one(wt)
        run_cmd(["git", "worktree", "prune"], cwd=self.repo)
        # Apoptosis should leave no empty per-run clone directory behind.
        for path in (self.root, self.root.parent):
            try:
                path.rmdir()
            except OSError:
                pass
