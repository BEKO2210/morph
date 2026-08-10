from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path

from ..util import clip, run_shell


@dataclass
class CheckResult:
    command: str
    passed: bool
    returncode: int
    duration_s: float
    stdout: str
    stderr: str

    def to_dict(self) -> dict:
        return asdict(self)


def run_check(repo: Path, command: str, timeout: int) -> CheckResult:
    try:
        r = run_shell(command, cwd=repo, timeout=timeout)
        return CheckResult(command, r.returncode == 0, r.returncode, r.duration_s, clip(r.stdout), clip(r.stderr))
    except Exception as exc:
        return CheckResult(command, False, 124, float(timeout), "", str(exc))


def run_checks(repo: Path, commands: list[str], timeout: int) -> list[CheckResult]:
    return [run_check(repo, command, timeout) for command in commands]


def pass_ratio(results: list[CheckResult]) -> float:
    if not results:
        return 0.60  # unknown is neither success nor failure
    return sum(r.passed for r in results) / len(results)
