import io
import json
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from morph.cli import doctor, main
from morph.config import MorphConfig


class DoctorOutput(unittest.TestCase):
    def test_json_mode_is_valid_json_with_expected_keys(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
            buf = io.StringIO()
            with redirect_stdout(buf):
                doctor(repo, as_json=True)
            data = json.loads(buf.getvalue())
            for key in ("python", "git", "claude", "codex", "is_git_repo"):
                self.assertIn(key, data)

    def test_human_mode_is_the_default_and_not_raw_json(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)  # deliberately not a git repo
            buf = io.StringIO()
            with redirect_stdout(buf):
                doctor(repo)  # as_json defaults to False
            out = buf.getvalue()
            self.assertFalse(out.strip().startswith("{"), "doctor() without --json must not print raw JSON")
            self.assertIn("git repository", out)

    def test_human_mode_gives_actionable_guidance_for_missing_pieces(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            with patch("morph.util.which", side_effect=lambda name: "/usr/bin/git" if name == "git" else None):
                buf = io.StringIO()
                with redirect_stdout(buf):
                    doctor(repo)
                out = buf.getvalue()
            # A newcomer with neither claude nor codex installed must be told
            # exactly what command to run, not just "codex: no".
            self.assertIn("npm install -g @openai/codex", out)
            self.assertIn("npm install -g @anthropic-ai/claude-code", out)


class RunFlagOverrides(unittest.TestCase):
    def test_clones_and_evolution_flags_override_config_without_editing_morph_yaml(self):
        captured = {}

        def fake_run_once(repo, task, adapter_name, cfg, **kwargs):
            captured["cfg"] = cfg
            return {"status": "winner-selected", "run_id": "x"}

        with patch("morph.cli.run_once", fake_run_once), patch("morph.cli.load_config", return_value=MorphConfig()):
            main(["run", "--adapter", "mock", "--clones", "5", "--evolution", "0", "--evolution-children", "2", "do the task"])

        cfg = captured["cfg"]
        self.assertEqual(cfg.clones, 5)
        self.assertEqual(cfg.clone_evolution, 0)
        self.assertEqual(cfg.evolution_children, 2)

    def test_without_flags_config_defaults_pass_through_unchanged(self):
        captured = {}

        def fake_run_once(repo, task, adapter_name, cfg, **kwargs):
            captured["cfg"] = cfg
            return {"status": "winner-selected", "run_id": "x"}

        with patch("morph.cli.run_once", fake_run_once), patch("morph.cli.load_config", return_value=MorphConfig()):
            main(["run", "--adapter", "mock", "do the task"])

        cfg = captured["cfg"]
        self.assertEqual(cfg.clones, 3)
        self.assertEqual(cfg.clone_evolution, 1)
        self.assertEqual(cfg.evolution_children, 3)


if __name__ == "__main__":
    unittest.main()
