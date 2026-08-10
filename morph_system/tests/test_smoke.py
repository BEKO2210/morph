from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


class Smoke(unittest.TestCase):
    def test_mock_one_shot(self):
        root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td) / "repo"
            repo.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
            (repo / "hello.txt").write_text("hello\n")
            subprocess.run(["git", "add", "."], cwd=repo, check=True)
            subprocess.run(["git", "-c", "user.name=T", "-c", "user.email=t@x", "commit", "-qm", "init"], cwd=repo, check=True)
            env = {**os.environ, "PYTHONPATH": str(root / "morph_system")}
            r = subprocess.run(
                ["python3", "-m", "morph", "run", "--repo", str(repo), "--adapter", "mock", "--apply", "make a mock repair"],
                text=True, capture_output=True, env=env,
            )
            self.assertEqual(r.returncode, 0, r.stderr)
            data = json.loads(r.stdout)
            self.assertEqual(data["status"], "winner-selected")
            self.assertTrue((repo / "MORPH_MOCK_CHANGE.txt").exists())
            self.assertFalse((repo / ".morph-worktrees").exists(), "temporary worktree directory should be fully removed")

    def test_failed_check_blocks_apply(self):
        root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td) / "repo"
            repo.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
            (repo / "hello.txt").write_text("hello\n")
            subprocess.run(["git", "add", "."], cwd=repo, check=True)
            subprocess.run(["git", "-c", "user.name=T", "-c", "user.email=t@x", "commit", "-qm", "init"], cwd=repo, check=True)
            (repo / "morph.yaml").write_text(json.dumps({"test_commands": ["python3 -c 'import sys; sys.exit(7)'"], "fitness_threshold": 0.0}))
            env = {**os.environ, "PYTHONPATH": str(root / "morph_system")}
            r = subprocess.run(
                ["python3", "-m", "morph", "run", "--repo", str(repo), "--adapter", "mock", "--apply", "make a mock repair"],
                text=True, capture_output=True, env=env,
            )
            self.assertEqual(r.returncode, 3, r.stderr)
            data = json.loads(r.stdout)
            self.assertEqual(data["status"], "no-winner-verification-failed")
            self.assertFalse(data["applied"])
            self.assertFalse((repo / "MORPH_MOCK_CHANGE.txt").exists())
            self.assertFalse((repo / ".morph-worktrees").exists())


if __name__ == "__main__":
    unittest.main()
