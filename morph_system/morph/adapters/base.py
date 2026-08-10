from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Callable


class AgentAdapter(ABC):
    name = "base"

    @abstractmethod
    def available(self) -> bool: ...

    @abstractmethod
    def build(
        self, cwd: Path, prompt: str, *,
        log_path: Path | None = None,
        report: Callable[[str], None] | None = None,
        echo: bool = False,
        retries: int = 2,
        backoff_s: float = 5.0,
        heartbeat_s: float = 20.0,
    ) -> str: ...

    @abstractmethod
    def review(
        self, cwd: Path, prompt: str, *,
        log_path: Path | None = None,
        report: Callable[[str], None] | None = None,
        echo: bool = False,
        retries: int = 2,
        backoff_s: float = 5.0,
        heartbeat_s: float = 20.0,
    ) -> str: ...
