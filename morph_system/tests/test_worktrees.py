import subprocess
import tempfile
import unittest
from pathlib import Path

from morph.git.worktrees import WorktreeManager


class WorktreeDependencyInheritance(unittest.TestCase):
    def _repo(self, td: str) -> Path:
        repo = Path(td)
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        (repo / "hello.txt").write_text("hello\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=repo, check=True)
        subprocess.run(["git", "-c", "user.name=T", "-c", "user.email=t@x", "commit", "-qm", "init"], cwd=repo, check=True)
        return repo

    def test_node_modules_is_available_in_a_fresh_worktree(self):
        # git worktree add never carries over gitignored directories, so
        # without this, "npm run lint"/"npm run build" inside a candidate
        # worktree would fail with "command not found" on every task that
        # doesn't itself happen to run npm install — even a perfectly
        # correct patch would then be rejected by the checks_ok gate.
        with tempfile.TemporaryDirectory() as td:
            repo = self._repo(td)
            (repo / "node_modules").mkdir()
            (repo / "node_modules" / "some-dep.js").write_text("module.exports = {};\n", encoding="utf-8")

            base = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, text=True, capture_output=True, check=True).stdout.strip()
            manager = WorktreeManager(repo, "testrun")
            try:
                wt = manager.create("clone-a", base)
                marker = wt.path / "node_modules" / "some-dep.js"
                self.assertTrue(marker.exists(), "node_modules was not inherited into the new worktree")
                self.assertEqual(marker.read_text(encoding="utf-8"), "module.exports = {};\n")
                self.assertEqual(manager.changed_files(wt), [])
                self.assertEqual(manager.patch(wt), "")
            finally:
                manager.cleanup_all()

    def test_worktree_without_node_modules_in_base_repo_is_unaffected(self):
        with tempfile.TemporaryDirectory() as td:
            repo = self._repo(td)
            base = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, text=True, capture_output=True, check=True).stdout.strip()
            manager = WorktreeManager(repo, "testrun")
            try:
                wt = manager.create("clone-a", base)
                self.assertFalse((wt.path / "node_modules").exists())
            finally:
                manager.cleanup_all()


if __name__ == "__main__":
    unittest.main()
