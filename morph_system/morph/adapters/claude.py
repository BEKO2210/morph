from __future__ import annotations

from pathlib import Path

from .base import AgentAdapter
from ..util import run_cmd, which


class ClaudeAdapter(AgentAdapter):
    name = "claude"

    def __init__(self, cfg: dict, timeout: int):
        self.cfg = cfg
        self.timeout = timeout

    def available(self) -> bool:
        return which("claude") is not None

    def _run(self, cwd: Path, prompt: str, write: bool) -> str:
        tools = self.cfg.get("builder_allowed_tools" if write else "review_allowed_tools", [])
        cmd = [
            "claude", "-p", "--no-session-persistence",
            "--model", str(self.cfg.get("model", "sonnet")),
            "--max-turns", str(self.cfg.get("max_turns", 18)),
            "--permission-mode", "acceptEdits" if write else "plan",
        ]
        if tools:
            cmd += ["--tools", ",".join(tools)]
        cmd.append(prompt)
        r = run_cmd(cmd, cwd=cwd, timeout=self.timeout)
        if r.returncode != 0:
            raise RuntimeError(f"Claude Code failed: {r.stderr.strip() or r.stdout.strip()}")
        return r.stdout.strip()

    def build(self, cwd: Path, prompt: str) -> str:
        return self._run(cwd, prompt, True)

    def review(self, cwd: Path, prompt: str) -> str:
        return self._run(cwd, prompt, False)
