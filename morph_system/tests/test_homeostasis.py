import subprocess
import tempfile
import unittest
from pathlib import Path

from morph.core.homeostasis import sense

IGNORE_PATHS = [".morph/", ".morph-worktrees/", "morph_system/", "morph-once", "morph.yaml"]


class Homeostasis(unittest.TestCase):
    def _repo(self, td: str) -> Path:
        repo = Path(td)
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        (repo / "hello.txt").write_text("hello\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=repo, check=True)
        subprocess.run(["git", "-c", "user.name=T", "-c", "user.email=t@x", "commit", "-qm", "init"], cwd=repo, check=True)
        return repo

    def test_own_untracked_artifacts_do_not_dirty_git_clean(self):
        with tempfile.TemporaryDirectory() as td:
            repo = self._repo(td)
            (repo / "morph.yaml").write_text("{}\n", encoding="utf-8")
            (repo / ".morph").mkdir()
            (repo / ".morph" / "runs.json").write_text("{}\n", encoding="utf-8")

            dirty = sense(repo, ignore_paths=IGNORE_PATHS)
            self.assertEqual(dirty.git_clean, 1.0)
            self.assertEqual(dirty.changed_files, 0)

    def test_real_project_changes_still_count_as_dirty(self):
        with tempfile.TemporaryDirectory() as td:
            repo = self._repo(td)
            (repo / "hello.txt").write_text("hello, changed\n", encoding="utf-8")

            dirty = sense(repo, ignore_paths=IGNORE_PATHS)
            self.assertEqual(dirty.git_clean, 0.0)

    def test_file_ignore_does_not_hide_similarly_prefixed_project_file(self):
        with tempfile.TemporaryDirectory() as td:
            repo = self._repo(td)
            (repo / "morph.yaml.backup").write_text("project data\n", encoding="utf-8")

            dirty = sense(repo, ignore_paths=IGNORE_PATHS)
            self.assertEqual(dirty.git_clean, 0.0)

    def test_without_ignore_paths_own_artifacts_still_count_dirty(self):
        # Sanity check that the fix is the ignore_paths filtering itself,
        # not some unrelated change to how status is read.
        with tempfile.TemporaryDirectory() as td:
            repo = self._repo(td)
            (repo / "morph.yaml").write_text("{}\n", encoding="utf-8")

            dirty = sense(repo)
            self.assertEqual(dirty.git_clean, 0.0)


if __name__ == "__main__":
    unittest.main()
