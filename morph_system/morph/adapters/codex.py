from __future__ import annotations

from pathlib import Path

from .base import AgentAdapter
from ..util import run_cmd, which


class CodexAdapter(AgentAdapter):
    name = "codex"

    def __init__(self, cfg: dict, timeout: int):
        self.cfg = cfg
        self.timeout = timeout

    def available(self) -> bool:
        return which("codex") is not None

    def _run(self, cwd: Path, prompt: str, write: bool) -> str:
        sandbox = str(self.cfg.get("sandbox", "workspace-write")) if write else "read-only"
        cmd = ["codex", "exec", "--ephemeral", "--sandbox", sandbox, "--ask-for-approval", "never", prompt]
        r = run_cmd(cmd, cwd=cwd, timeout=self.timeout)
        if r.returncode != 0:
            raise RuntimeError(f"Codex failed: {r.stderr.strip() or r.stdout.strip()}")
        return r.stdout.strip()

    def build(self, cwd: Path, prompt: str) -> str:
        return self._run(cwd, prompt, True)

    def review(self, cwd: Path, prompt: str) -> str:
        return self._run(cwd, prompt, False)
