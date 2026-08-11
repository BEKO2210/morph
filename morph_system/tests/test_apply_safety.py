import subprocess
import tempfile
import unittest
from pathlib import Path

from morph.colony.orchestrator import _apply_winner_patch


def _run(args, cwd):
    subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True)


def _init_repo(repo: Path, content: str) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    _run(["git", "init", "-q"], repo)
    (repo / "hello.txt").write_text(content, encoding="utf-8")
    _run(["git", "add", "."], repo)
    _run(["git", "-c", "user.name=T", "-c", "user.email=t@x", "commit", "-qm", "init"], repo)


class ApplySafety(unittest.TestCase):
    def test_clean_patch_applies(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            _init_repo(repo, "line1\nline2\nline3\n")
            (repo / "hello.txt").write_text("line1\nCHANGED\nline3\n", encoding="utf-8")
            patch = subprocess.run(["git", "diff"], cwd=repo, capture_output=True, text=True, check=True).stdout
            _run(["git", "checkout", "--", "hello.txt"], repo)
            patch_path = repo / "winner.patch"
            patch_path.write_text(patch, encoding="utf-8")

            _apply_winner_patch(repo, patch_path)

            self.assertEqual((repo / "hello.txt").read_text(encoding="utf-8"), "line1\nCHANGED\nline3\n")

    def test_unapplicable_patch_never_touches_the_working_tree(self):
        # Build a patch against content A, but apply it to a repo whose
        # current file content is C (unrelated to A) — neither --3way nor
        # plain apply can succeed. Before the fix, the --3way attempt could
        # still partially mutate hello.txt before failing, and the
        # immediate plain-apply retry against that half-mutated file could
        # corrupt it further (including deleting it). The fix must leave
        # the working tree byte-for-byte untouched.
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            _init_repo(repo, "alpha\nbeta\ngamma\ndelta\nepsilon\n")
            (repo / "hello.txt").write_text("alpha\nBETA-CHANGED\ngamma\ndelta\nepsilon\n", encoding="utf-8")
            patch = subprocess.run(["git", "diff"], cwd=repo, capture_output=True, text=True, check=True).stdout
            _run(["git", "checkout", "--", "hello.txt"], repo)
            patch_path = repo / "winner.patch"
            patch_path.write_text(patch, encoding="utf-8")

            # Now make the working tree diverge from what the patch expects,
            # in a way that is unrelated to the patched region.
            (repo / "hello.txt").write_text("totally-different-content\nno-relation-at-all\n", encoding="utf-8")
            before = (repo / "hello.txt").read_text(encoding="utf-8")
            status_before = subprocess.run(["git", "status", "--porcelain"], cwd=repo, capture_output=True, text=True, check=True).stdout

            with self.assertRaises(RuntimeError):
                _apply_winner_patch(repo, patch_path)

            after = (repo / "hello.txt").read_text(encoding="utf-8")
            status_after = subprocess.run(["git", "status", "--porcelain"], cwd=repo, capture_output=True, text=True, check=True).stdout
            self.assertEqual(before, after, "working tree file was mutated by a failed apply attempt")
            self.assertEqual(status_before, status_after, "git status changed as a side effect of a failed apply attempt")

    def test_falls_back_to_3way_when_plain_apply_would_fail(self):
        # A patch whose context lines have drifted (an unrelated edit
        # elsewhere in the file) still merges cleanly via --3way even
        # though a plain `git apply` would reject it for context mismatch.
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            _init_repo(repo, "\n".join(f"line{i}" for i in range(1, 21)) + "\n")
            base_sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True).stdout.strip()

            (repo / "hello.txt").write_text(
                "\n".join(f"line{i}" for i in range(1, 21)).replace("line5", "line5-CHANGED") + "\n",
                encoding="utf-8",
            )
            patch = subprocess.run(["git", "diff"], cwd=repo, capture_output=True, text=True, check=True).stdout
            _run(["git", "checkout", "--", "hello.txt"], repo)
            patch_path = repo / "winner.patch"
            patch_path.write_text(patch, encoding="utf-8")

            # Drift the base with an unrelated, far-away edit + a new commit
            # (so plain `git apply`, which requires exact context, no
            # longer matches — but --3way can reconcile it against the
            # common ancestor).
            (repo / "hello.txt").write_text(
                "\n".join(f"line{i}" for i in range(1, 21)).replace("line15", "line15-UNRELATED-EDIT") + "\n",
                encoding="utf-8",
            )
            _run(["git", "add", "."], repo)
            _run(["git", "-c", "user.name=T", "-c", "user.email=t@x", "commit", "-qm", "unrelated"], repo)

            _apply_winner_patch(repo, patch_path)

            result = (repo / "hello.txt").read_text(encoding="utf-8")
            self.assertIn("line5-CHANGED", result)
            self.assertIn("line15-UNRELATED-EDIT", result)


if __name__ == "__main__":
    unittest.main()
