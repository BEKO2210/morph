import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


class ProgressOutput(unittest.TestCase):
    def test_progress_events_stream_on_stderr_stdout_stays_pure_json(self):
        root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td) / "repo"
            repo.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
            (repo / "hello.txt").write_text("hello\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=repo, check=True)
            subprocess.run(["git", "-c", "user.name=T", "-c", "user.email=t@x", "commit", "-qm", "init"], cwd=repo, check=True)
            env = {**os.environ, "PYTHONPATH": str(root / "morph_system")}
            r = subprocess.run(
                ["python3", "-m", "morph", "run", "--repo", str(repo), "--adapter", "mock", "make a mock repair"],
                text=True, capture_output=True, env=env,
            )
            self.assertEqual(r.returncode, 0, r.stderr)

            # stdout must stay pure, parseable JSON — nothing else was ever
            # printed to it, so downstream tooling (jq, CI) can rely on it.
            data = json.loads(r.stdout)
            self.assertEqual(data["status"], "winner-selected")

            # Live progress must be visible on stderr as the run happens,
            # not only after the fact.
            progress_lines = [l for l in r.stderr.splitlines() if l.startswith("[MORPH]")]
            self.assertGreater(len(progress_lines), 0, "no [MORPH] progress lines were emitted")
            joined = "\n".join(progress_lines)
            self.assertIn("Sensing repository", joined)
            self.assertIn("Builder started", joined)
            self.assertIn("Builder completed", joined)
            self.assertIn("Cleaning worktrees", joined)

            # The same events were journaled to disk for post-hoc review.
            run_dir = repo / data["run_dir"]
            progress_log = (run_dir / "progress.log").read_text(encoding="utf-8")
            self.assertIn("Sensing repository", progress_log)


if __name__ == "__main__":
    unittest.main()
