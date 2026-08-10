from __future__ import annotations

from pathlib import Path
from .base import AgentAdapter


class MockAdapter(AgentAdapter):
    name = "mock"

    def available(self) -> bool:
        return True

    def _write_log(self, log_path: Path | None, text: str) -> None:
        if log_path:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_path.write_text(text + "\n", encoding="utf-8")

    def build(self, cwd: Path, prompt: str, **kwargs) -> str:
        marker = cwd / "MORPH_MOCK_CHANGE.txt"
        marker.write_text("mock repair candidate\n", encoding="utf-8")
        text = "Mock builder created MORPH_MOCK_CHANGE.txt"
        self._write_log(kwargs.get("log_path"), text)
        return text

    def review(self, cwd: Path, prompt: str, **kwargs) -> str:
        if "HYPOTHESES" in prompt:
            out = '[{"name":"direct","theory":"direct implementation"},{"name":"interface","theory":"interface mismatch"},{"name":"latent","theory":"latent regression"}]'
        else:
            out = '{"severity":0.1,"confidence":0.9,"findings":[]}'
        self._write_log(kwargs.get("log_path"), out)
        return out
