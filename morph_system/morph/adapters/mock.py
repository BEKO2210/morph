from __future__ import annotations

from pathlib import Path
from .base import AgentAdapter


class MockAdapter(AgentAdapter):
    name = "mock"
    def available(self) -> bool:
        return True
    def build(self, cwd: Path, prompt: str) -> str:
        marker = cwd / "MORPH_MOCK_CHANGE.txt"
        marker.write_text("mock repair candidate\n", encoding="utf-8")
        return "Mock builder created MORPH_MOCK_CHANGE.txt"
    def review(self, cwd: Path, prompt: str) -> str:
        if "HYPOTHESES" in prompt:
            return '[{"name":"direct","theory":"direct implementation"},{"name":"interface","theory":"interface mismatch"},{"name":"latent","theory":"latent regression"}]'
        return '{"severity":0.1,"confidence":0.9,"findings":[]}'
