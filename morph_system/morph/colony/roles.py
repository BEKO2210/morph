from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from ..adapters.base import AgentAdapter
from ..util import extract_json, run_cmd, clip


@dataclass
class Review:
    severity: float
    confidence: float
    findings: list[str]
    raw: str


def _diff(cwd: Path, base: str) -> str:
    return clip(run_cmd(["git", "diff", "--no-ext-diff", base, "--"], cwd=cwd).stdout, 18000)


def builder(
    adapter: AgentAdapter, cwd: Path, task: str, hypothesis: str,
    stress: list[tuple[str, float]], antibodies: list[dict], **agent_kwargs,
) -> str:
    stress_text = "\n".join(f"- {p}: {v:.2f}" for p, v in stress[:20]) or "- none yet"
    memory_text = "\n".join(f"- {a.get('diagnosis','?')}: {a.get('repair_strategy','?')}" for a in antibodies[-8:]) or "- none"
    prompt = f"""You are BUILDER, one cell in MORPH. Work ONLY in the current git worktree.\n\nUSER TASK:\n{task}\n\nCAUSAL HYPOTHESIS TO PURSUE:\n{hypothesis}\n\nHIGH-STRESS REPOSITORY AREAS:\n{stress_text}\n\nRELEVANT IMMUNE MEMORY (advice, never blindly copy):\n{memory_text}\n\nRules:\n1. Implement the task completely, not just explain it.\n2. Prefer the smallest root-cause patch that preserves existing behavior.\n3. Do not commit, push, change git remotes, install global software, read secrets, or modify files outside this worktree.\n4. Do not weaken or delete tests to obtain green status.\n5. Avoid new dependencies unless genuinely necessary.\n6. Finish by summarizing what you changed and remaining uncertainty.\n\nEdit the repository now."""
    return adapter.build(cwd, prompt, **agent_kwargs)


def predator(adapter: AgentAdapter, cwd: Path, base: str, task: str, **agent_kwargs) -> Review:
    diff = _diff(cwd, base)
    prompt = f"""You are PREDATOR in MORPH. You do not help the patch. You try to falsify it. Do not edit files.\nTask: {task}\nCandidate diff:\n{diff}\n\nLook for realistic regressions, edge cases, platform issues, malformed input, concurrency/state bugs, security invariant violations, API mismatches, and tests that were gamed.\nReturn ONLY JSON: {{\"severity\":0.0-1.0,\"confidence\":0.0-1.0,\"findings\":[\"...\"]}}. Severity 0 means you found no credible break; 1 means fatal."""
    raw = adapter.review(cwd, prompt, **agent_kwargs)
    data = extract_json(raw) or {}
    return Review(float(data.get("severity", 0.5)), float(data.get("confidence", 0.5)), [str(x) for x in data.get("findings", [])][:20], raw)


def guardian(adapter: AgentAdapter, cwd: Path, base: str, task: str, **agent_kwargs) -> Review:
    diff = _diff(cwd, base)
    prompt = f"""You are GUARDIAN in MORPH. Protect repository homeostasis. Do not edit files.\nTask: {task}\nCandidate diff:\n{diff}\n\nJudge over-repair, needless file churn, dependency changes, public API drift, complexity growth, suspicious lockfile/config changes, removed behavior, test weakening, and whether the patch is minimal for the task.\nReturn ONLY JSON: {{\"severity\":0.0-1.0,\"confidence\":0.0-1.0,\"findings\":[\"...\"]}}. Severity 0 means homeostasis is preserved; 1 means unacceptable damage."""
    raw = adapter.review(cwd, prompt, **agent_kwargs)
    data = extract_json(raw) or {}
    return Review(float(data.get("severity", 0.5)), float(data.get("confidence", 0.5)), [str(x) for x in data.get("findings", [])][:20], raw)
