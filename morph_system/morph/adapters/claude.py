from __future__ import annotations

from pathlib import Path
from typing import Callable

from .base import AgentAdapter
from ..util import run_agent, which


class ClaudeAdapter(AgentAdapter):
    name = "claude"

    def __init__(self, cfg: dict, timeout: int):
        self.cfg = cfg
        self.timeout = timeout

    def available(self) -> bool:
        return which("claude") is not None

    def _run(
        self, cwd: Path, prompt: str, write: bool, *,
        log_path: Path | None = None,
        report: Callable[[str], None] | None = None,
        echo: bool = False,
        retries: int = 2,
        backoff_s: float = 5.0,
        heartbeat_s: float = 20.0,
    ) -> str:
        tools = self.cfg.get("builder_allowed_tools" if write else "review_allowed_tools", [])
        cmd = [
            "claude", "-p", "--no-session-persistence",
            "--model", str(self.cfg.get("model", "sonnet")),
            "--max-turns", str(self.cfg.get("max_turns", 18)),
            "--permission-mode", "acceptEdits" if write else "plan",
        ]
        if tools:
            cmd += ["--tools", ",".join(tools)]
        # claude's --tools flag is variadic and greedily consumes the next
        # argv token; without an explicit end-of-options marker it swallows
        # the prompt itself, leaving claude -p with no prompt at all.
        cmd += ["--", prompt]
        r = run_agent(
            cmd, cwd=cwd, timeout=self.timeout, log_path=log_path, echo=echo,
            label="claude builder" if write else "claude review", report=report,
            retries=retries, backoff_s=backoff_s, heartbeat_s=heartbeat_s,
        )
        if r.returncode != 0:
            raise RuntimeError(f"Claude Code failed: {r.stdout.strip()[-4000:]}")
        return r.stdout.strip()

    def build(self, cwd: Path, prompt: str, **kwargs) -> str:
        return self._run(cwd, prompt, True, **kwargs)

    def review(self, cwd: Path, prompt: str, **kwargs) -> str:
        return self._run(cwd, prompt, False, **kwargs)
