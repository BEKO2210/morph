from __future__ import annotations

import json
import time
from pathlib import Path

from ..util import json_dump, json_load, stable_id


class MemoryStore:
    def __init__(self, repo: Path):
        self.root = repo / ".morph" / "memory"
        self.root.mkdir(parents=True, exist_ok=True)

    def antibodies(self) -> list[dict]:
        return json_load(self.root / "antibodies.json", [])

    def add_antibody(self, item: dict) -> None:
        items = self.antibodies()
        item = {**item, "id": stable_id(json.dumps(item, sort_keys=True)), "created_at": int(time.time())}
        items.append(item)
        json_dump(self.root / "antibodies.json", items[-250:])

    def pheromones(self) -> dict[str, dict]:
        return json_load(self.root / "pheromones.json", {})

    def deposit(self, files: list[str], signal: str, strength: float, decay: float = 0.82) -> None:
        data = self.pheromones()
        for path, entry in list(data.items()):
            entry["strength"] = round(float(entry.get("strength", 0.0)) * decay, 4)
            if entry["strength"] < 0.03:
                data.pop(path, None)
        now = int(time.time())
        for path in files:
            e = data.setdefault(path, {"strength": 0.0, "signals": []})
            e["strength"] = round(min(1.0, float(e.get("strength", 0.0)) + strength), 4)
            e["updated_at"] = now
            e.setdefault("signals", []).append(signal)
            e["signals"] = e["signals"][-8:]
        json_dump(self.root / "pheromones.json", data)

    def trust(self) -> dict[str, dict]:
        return json_load(self.root / "trust.json", {})

    def update_trust(self, files: list[str], healthy: bool) -> None:
        """Hysteretic trust: damage is fast; recovery requires repeated healthy passes."""
        data = self.trust()
        now = int(time.time())
        for path in files:
            e = data.setdefault(path, {"state": "normal", "healthy_streak": 0, "score": 1.0})
            if healthy:
                e["healthy_streak"] = int(e.get("healthy_streak", 0)) + 1
                e["score"] = round(min(1.0, float(e.get("score", 1.0)) + 0.08), 3)
                if e["healthy_streak"] >= 3 and e["score"] >= 0.85:
                    e["state"] = "normal"
            else:
                e["healthy_streak"] = 0
                e["score"] = round(max(0.0, float(e.get("score", 1.0)) - 0.35), 3)
                e["state"] = "low"
            e["updated_at"] = now
        json_dump(self.root / "trust.json", data)
