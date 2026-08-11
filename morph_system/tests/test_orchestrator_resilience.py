import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from morph.adapters.base import AgentAdapter
from morph.colony.orchestrator import _apply_winner_patch, run_once
from morph.config import MorphConfig


def _init_repo(path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    (path / "hello.txt").write_text("hello\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=path, check=True)
    subprocess.run(["git", "-c", "user.name=T", "-c", "user.email=t@x", "commit", "-qm", "init"], cwd=path, check=True)


def _single_clone_cfg() -> MorphConfig:
    cfg = MorphConfig()
    cfg.clones = 1
    cfg.clone_evolution = 0
    cfg.evolution_children = 0
    cfg.test_commands = []
    cfg.fitness_threshold = 0.0
    return cfg


class AlwaysFailReviewAdapter(AgentAdapter):
    """Builder always succeeds; every Predator/Guardian review() call
    raises, simulating a persistently broken review path (e.g. the real
    Codex process dying mid-run to a dropped websocket)."""

    name = "fail-review"

    def available(self) -> bool:
        return True

    def build(self, cwd, prompt, **kwargs):
        (Path(cwd) / "CHANGED.txt").write_text("candidate change\n", encoding="utf-8")
        log_path = kwargs.get("log_path")
        if log_path:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_path.write_text("builder ran fine\n", encoding="utf-8")
        return "built ok"

    def review(self, cwd, prompt, **kwargs):
        if "HYPOTHESES" in prompt:
            return '[{"name":"only","theory":"only hypothesis"}]'
        raise RuntimeError("Codex failed: stream disconnected before completion")


class NoChangeAdapter(AgentAdapter):
    """Builder never edits anything — MORPH sees an empty diff."""

    name = "no-change"

    def available(self) -> bool:
        return True

    def build(self, cwd, prompt, **kwargs):
        return "builder decided there was nothing to change"

    def review(self, cwd, prompt, **kwargs):
        if "HYPOTHESES" in prompt:
            return '[{"name":"only","theory":"only hypothesis"}]'
        raise AssertionError("predator/guardian must never run for a builder-no-change candidate")


class OrchestratorResilience(unittest.TestCase):
    def test_patch_apply_preflights_before_mutating_base_tree(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            patch_file = repo / "winner.patch"
            patch_file.write_text("not a patch\n", encoding="utf-8")

            with patch("morph.colony.orchestrator.run_cmd") as run:
                run.side_effect = [
                    subprocess.CompletedProcess([], 1, "", "plain rejected"),
                    subprocess.CompletedProcess([], 1, "", "three-way rejected"),
                ]
                with self.assertRaisesRegex(RuntimeError, "could not be applied"):
                    _apply_winner_patch(repo, patch_file)

            commands = [call.args[0] for call in run.call_args_list]
            self.assertEqual(
                commands,
                [
                    ["git", "apply", "--check", str(patch_file)],
                    ["git", "apply", "--3way", "--check", str(patch_file)],
                ],
            )

    def test_patch_apply_uses_three_way_fallback_only_after_successful_preflight(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            patch_file = repo / "winner.patch"
            patch_file.write_text("patch\n", encoding="utf-8")

            with patch("morph.colony.orchestrator.run_cmd") as run:
                run.side_effect = [
                    subprocess.CompletedProcess([], 1, "", "plain rejected"),
                    subprocess.CompletedProcess([], 0, "", ""),
                    subprocess.CompletedProcess([], 0, "", ""),
                ]
                _apply_winner_patch(repo, patch_file)

            commands = [call.args[0] for call in run.call_args_list]
            self.assertEqual(
                commands,
                [
                    ["git", "apply", "--check", str(patch_file)],
                    ["git", "apply", "--3way", "--check", str(patch_file)],
                    ["git", "apply", "--3way", str(patch_file)],
                ],
            )

    def test_persistent_review_failure_degrades_candidate_without_crashing_run(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            _init_repo(repo)
            with patch("morph.colony.orchestrator.make_adapter", return_value=AlwaysFailReviewAdapter()):
                result = run_once(repo, "do the task", "fail-review", _single_clone_cfg(), apply=False, commit=False, push=False)

            # The run must complete and report a controlled outcome, not
            # blow up because one review call failed.
            self.assertEqual(result["candidate_count"], 1)
            self.assertNotEqual(result["status"], "run-failed")

            cand = json.loads((repo / result["run_dir"] / "g0-candidate-1.json").read_text())
            self.assertEqual(cand["status"], "scored")
            self.assertEqual(cand["predator"]["severity"], 1.0)
            self.assertIn("predator-review-failed", cand["predator"]["findings"][0])
            self.assertEqual(cand["guardian"]["severity"], 1.0)

            # Builder work already done before the review died is preserved
            # on disk, not thrown away with the rest of the candidate.
            self.assertTrue((repo / result["run_dir"] / "g0-candidate-1.patch").read_text().strip())
            self.assertIn("builder ran fine", (repo / result["run_dir"] / "g0-candidate-1.builder.log").read_text())

            # A persistently broken review must block the candidate from
            # winning, traceably (gate is false, not just a low score).
            gates = result["selection_gates"]
            self.assertFalse(gates["predator_ok"])
            self.assertEqual(result["status"], "no-winner-verification-failed")

    def test_empty_builder_diff_is_explicit_state_not_silently_scored(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            _init_repo(repo)
            with patch("morph.colony.orchestrator.make_adapter", return_value=NoChangeAdapter()):
                result = run_once(repo, "do nothing useful", "no-change", _single_clone_cfg(), apply=False, commit=False, push=False)

            self.assertEqual(result["status"], "no-viable-candidate")
            self.assertIsNone(result["winner"])
            cand = json.loads((repo / result["run_dir"] / "g0-candidate-1.json").read_text())
            self.assertEqual(cand["status"], "builder-no-change")
            # NoChangeAdapter.review() raises an AssertionError if it is ever
            # called for review; run_once completing at all proves it wasn't.

    def test_unexpected_exception_still_writes_result_and_error_and_cleans_up(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            _init_repo(repo)
            with patch("morph.colony.orchestrator.compute", side_effect=RuntimeError("boom-fitness")):
                with self.assertRaises(RuntimeError):
                    run_once(repo, "do the task", "mock", _single_clone_cfg(), apply=False, commit=False, push=False)

            runs = list((repo / ".morph" / "runs").iterdir())
            self.assertEqual(len(runs), 1)
            run_dir = runs[0]

            result = json.loads((run_dir / "result.json").read_text())
            self.assertEqual(result["status"], "run-failed")
            error = json.loads((run_dir / "error.json").read_text())
            self.assertIn("boom-fitness", error["message"])

            # Builder work up to the failure point survives the crash.
            self.assertTrue((run_dir / "g0-candidate-1.builder.log").exists())
            self.assertTrue((run_dir / "g0-candidate-1.patch").exists())

            # Apoptosis still runs on the exception path.
            wt_list = subprocess.run(["git", "worktree", "list"], cwd=repo, text=True, capture_output=True).stdout
            self.assertEqual(len(wt_list.strip().splitlines()), 1)
            branches = subprocess.run(["git", "branch", "--list", "morph/*"], cwd=repo, text=True, capture_output=True).stdout
            self.assertEqual(branches.strip(), "")
            self.assertFalse((repo / ".morph-worktrees").exists())


if __name__ == "__main__":
    unittest.main()
