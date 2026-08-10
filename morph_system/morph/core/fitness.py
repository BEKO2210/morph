from __future__ import annotations

from dataclasses import dataclass, asdict


@dataclass
class FitnessInputs:
    tests_ratio: float
    predator_score: float
    guardian_score: float
    minimality: float
    dependency_stability: float
    blast_radius: float
    task_signal: float


@dataclass
class FitnessResult:
    score: float
    components: dict[str, float]

    def to_dict(self) -> dict:
        return {"score": self.score, "components": self.components}


def compute(inputs: FitnessInputs, weights: dict[str, float]) -> FitnessResult:
    vals = asdict(inputs)
    # Config uses human-facing names (tests/predator/guardian) while the
    # dataclass names describe normalized scores. Keep the mapping explicit so
    # safety-critical signals can never silently receive weight zero.
    aliases = {
        "tests_ratio": "tests",
        "predator_score": "predator",
        "guardian_score": "guardian",
    }
    weighted: dict[str, float] = {}
    denom = 0.0
    for key, value in vals.items():
        weight_key = aliases.get(key, key)
        weight = float(weights.get(weight_key, 0.0))
        weighted[key] = max(0.0, min(1.0, float(value))) * weight
        denom += weight
    denom = denom or 1.0
    return FitnessResult(score=sum(weighted.values()) / denom, components=weighted)
