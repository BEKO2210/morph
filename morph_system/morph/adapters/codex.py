from __future__ import annotations

from pathlib import Path
from typing import Callable

from .base import AgentAdapter
from ..util import run_agent, which


class CodexAdapter(AgentAdapter):
    name = "codex"

    def __init__(self, cfg: dict, timeout: int):
        self.cfg = cfg
        self.timeout = timeout

    def available(self) -> bool:
        return which("codex") is not None

    def _run(
        self, cwd: Path, prompt: str, write: bool, *,
        log_path: Path | None = None,
        report: Callable[[str], None] | None = None,
        echo: bool = False,
        retries: int = 2,
        backoff_s: float = 5.0,
        heartbeat_s: float = 20.0,
    ) -> str:
        sandbox = str(self.cfg.get("sandbox", "workspace-write")) if write else "read-only"
        # --ask-for-approval is a GLOBAL codex option and must precede the
        # `exec` subcommand (codex >= 0.147). `codex exec --ask-for-approval`
        # is rejected with "unexpected argument '--ask-for-approval' found".
        cmd = [
            "codex", "--ask-for-approval", "never",
            "exec", "--ephemeral", "--sandbox", sandbox, prompt,
        ]
        r = run_agent(
            cmd, cwd=cwd, timeout=self.timeout, log_path=log_path, echo=echo,
            label="codex builder" if write else "codex review", report=report,
            retries=retries, backoff_s=backoff_s, heartbeat_s=heartbeat_s,
        )
        if r.returncode != 0:
            raise RuntimeError(f"Codex failed: {r.stdout.strip()[-4000:]}")
        return r.stdout.strip()

    def build(self, cwd: Path, prompt: str, **kwargs) -> str:
        return self._run(cwd, prompt, True, **kwargs)

    def review(self, cwd: Path, prompt: str, **kwargs) -> str:
        return self._run(cwd, prompt, False, **kwargs)
