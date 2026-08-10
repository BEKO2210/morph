from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class MorphConfig:
    clones: int = 3
    clone_evolution: int = 1
    evolution_children: int = 3
    timeout_seconds: int = 900
    max_changed_files: int = 40
    max_diff_lines: int = 2200
    fitness_threshold: float = 0.45
    require_clean_for_apply: bool = True
    test_commands: list[str] = field(default_factory=list)
    predator_commands: list[str] = field(default_factory=list)
    ignore_paths: list[str] = field(default_factory=lambda: [".morph/", ".morph-worktrees/", "morph_system/", "morph-once", "morph.yaml", "START-MORPH.txt", "CHECKSUMS.txt", ".gitignore.example", "node_modules/", ".venv/"])
    homeostasis: dict[str, float] = field(default_factory=lambda: {
        "tests": 0.32,
        "predator": 0.14,
        "guardian": 0.15,
        "minimality": 0.14,
        "dependency_stability": 0.10,
        "blast_radius": 0.08,
        "task_signal": 0.07,
    })
    claude: dict[str, Any] = field(default_factory=lambda: {
        "model": "sonnet",
        "max_turns": 18,
        "builder_allowed_tools": ["Read", "Edit", "Write", "Glob", "Grep"],
        "review_allowed_tools": ["Read", "Glob", "Grep"],
    })
    codex: dict[str, Any] = field(default_factory=lambda: {
        "sandbox": "workspace-write",
    })


def load_config(repo: Path) -> MorphConfig:
    cfg = MorphConfig()
    path = repo / "morph.yaml"
    if not path.exists():
        path = repo / "morph_system" / "morph.yaml"
    if not path.exists():
        return cfg
    raw = json.loads(path.read_text(encoding="utf-8"))
    for key, value in raw.items():
        if hasattr(cfg, key):
            setattr(cfg, key, value)
    return cfg
