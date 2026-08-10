from __future__ import annotations

from dataclasses import dataclass, asdict

from ..adapters.base import AgentAdapter
from ..util import extract_json


@dataclass
class Hypothesis:
    name: str
    theory: str

    def to_dict(self):
        return asdict(self)


FALLBACK = [
    Hypothesis("direct-cause", "The requested behavior is best solved by changing the most directly responsible implementation."),
    Hypothesis("interface-cause", "The failure or missing behavior originates at a module/API boundary rather than inside one function."),
    Hypothesis("latent-regression", "A latent defect already exists and the requested change merely exposes it; preserve compatibility while fixing root cause."),
    Hypothesis("environment-cause", "Tooling, configuration, dependency, path, platform, or CI assumptions are the primary cause."),
    Hypothesis("minimal-reframe", "The smallest correct repair is structurally different from the obvious patch and should minimize blast radius."),
]


def generate(adapter: AgentAdapter, cwd, task: str, repo_summary: str, count: int) -> list[Hypothesis]:
    prompt = f"""MORPH HYPOTHESES\nYou are the causal-diversity stage of a repair system.\nTask: {task}\nRepository summary:\n{repo_summary}\n\nReturn ONLY a JSON array of {count} objects with keys name and theory. Each theory must represent a materially different causal explanation or implementation strategy. Do not edit files."""
    try:
        data = extract_json(adapter.review(cwd, prompt))
        if isinstance(data, list):
            out = [Hypothesis(str(x.get("name", f"h{i}")), str(x.get("theory", ""))) for i, x in enumerate(data) if isinstance(x, dict)]
            if out:
                used = {h.name for h in out}
                for fallback in FALLBACK:
                    if len(out) >= count:
                        break
                    if fallback.name not in used:
                        out.append(fallback)
                        used.add(fallback.name)
                return out[:count]
    except Exception:
        pass
    return FALLBACK[:count]
