import unittest
from unittest.mock import patch

from morph.adapters.claude import ClaudeAdapter
from morph.util import CmdResult


class ClaudeAdapterArgs(unittest.TestCase):
    def test_prompt_is_isolated_from_variadic_tools_flag(self):
        # claude's --tools flag is variadic and greedily consumes argv tokens;
        # without a "--" end-of-options marker it swallows the prompt itself,
        # so this asserts the built command always separates the two.
        captured = {}

        def fake_run_agent(cmd, **kwargs):
            captured["cmd"] = cmd
            return CmdResult(cmd, 0, "ok", "", 0.0)

        adapter = ClaudeAdapter({"builder_allowed_tools": ["Read", "Edit"]}, timeout=60)
        with patch("morph.adapters.claude.run_agent", fake_run_agent):
            adapter.build(cwd=".", prompt="do the thing --tools-like-looking-prompt")

        cmd = captured["cmd"]
        self.assertIn("--", cmd)
        sep = cmd.index("--")
        self.assertEqual(cmd[sep + 1:], ["do the thing --tools-like-looking-prompt"])
        self.assertLess(cmd.index("--tools"), sep)


if __name__ == "__main__":
    unittest.main()
