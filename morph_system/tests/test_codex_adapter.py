import unittest
from unittest.mock import patch

from morph.adapters.codex import CodexAdapter
from morph.util import CmdResult


class CodexAdapterArgs(unittest.TestCase):
    def test_global_options_precede_exec_subcommand(self):
        # codex >= 0.147 rejects `codex exec --ask-for-approval ...` with
        # "unexpected argument '--ask-for-approval' found" because
        # --ask-for-approval is a GLOBAL option and must come before the
        # `exec` subcommand, not after it.
        captured = {}

        def fake_run_agent(cmd, **kwargs):
            captured["cmd"] = cmd
            return CmdResult(cmd, 0, "ok", "", 0.0)

        adapter = CodexAdapter({"sandbox": "workspace-write"}, timeout=60)
        with patch("morph.adapters.codex.run_agent", fake_run_agent):
            adapter.build(cwd=".", prompt="do the thing")

        cmd = captured["cmd"]
        self.assertIn("exec", cmd)
        self.assertIn("--ask-for-approval", cmd)
        exec_idx = cmd.index("exec")
        approval_idx = cmd.index("--ask-for-approval")
        self.assertLess(approval_idx, exec_idx, f"--ask-for-approval must precede exec, got: {cmd}")
        self.assertEqual(cmd[0], "codex")

    def test_review_uses_read_only_sandbox(self):
        captured = {}

        def fake_run_agent(cmd, **kwargs):
            captured["cmd"] = cmd
            return CmdResult(cmd, 0, "ok", "", 0.0)

        adapter = CodexAdapter({"sandbox": "workspace-write"}, timeout=60)
        with patch("morph.adapters.codex.run_agent", fake_run_agent):
            adapter.review(cwd=".", prompt="review this")

        cmd = captured["cmd"]
        sandbox_idx = cmd.index("--sandbox")
        self.assertEqual(cmd[sandbox_idx + 1], "read-only")


if __name__ == "__main__":
    unittest.main()
