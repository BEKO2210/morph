from __future__ import annotations

from .claude import ClaudeAdapter
from .codex import CodexAdapter
from .mock import MockAdapter


def make_adapter(name: str, cfg, timeout: int):
    if name == "claude":
        return ClaudeAdapter(cfg.claude, timeout)
    if name == "codex":
        return CodexAdapter(cfg.codex, timeout)
    if name == "mock":
        return MockAdapter()
    if name == "auto":
        for candidate in (ClaudeAdapter(cfg.claude, timeout), CodexAdapter(cfg.codex, timeout)):
            if candidate.available():
                return candidate
        raise RuntimeError("Neither Claude Code (`claude`) nor Codex (`codex`) was found in PATH.")
    raise RuntimeError(f"Unknown adapter: {name}")
