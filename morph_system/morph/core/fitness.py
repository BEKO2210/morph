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
    weighted = {k: max(0.0, min(1.0, float(vals[k]))) * float(weights.get(k, 0.0)) for k in vals}
    denom = sum(float(weights.get(k, 0.0)) for k in vals) or 1.0
    return FitnessResult(score=sum(weighted.values()) / denom, components=weighted)
