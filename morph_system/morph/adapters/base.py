from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class AgentAdapter(ABC):
    name = "base"

    @abstractmethod
    def available(self) -> bool: ...

    @abstractmethod
    def build(self, cwd: Path, prompt: str) -> str: ...

    @abstractmethod
    def review(self, cwd: Path, prompt: str) -> str: ...
