from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


@dataclass
class CmdResult:
    command: list[str]
    returncode: int
    stdout: str
    stderr: str
    duration_s: float


def run_cmd(
    command: list[str] | str,
    *,
    cwd: Path,
    timeout: int = 900,
    env: dict[str, str] | None = None,
    check: bool = False,
) -> CmdResult:
    args = shlex.split(command) if isinstance(command, str) else command
    started = time.monotonic()
    proc = subprocess.run(
        args,
        cwd=str(cwd),
        env={**os.environ, **(env or {})},
        text=True,
        capture_output=True,
        timeout=timeout,
    )
    result = CmdResult(args, proc.returncode, proc.stdout, proc.stderr, time.monotonic() - started)
    if check and proc.returncode != 0:
        raise RuntimeError(f"Command failed ({proc.returncode}): {' '.join(args)}\n{proc.stderr}")
    return result


def run_shell(command: str, *, cwd: Path, timeout: int = 900) -> CmdResult:
    started = time.monotonic()
    proc = subprocess.run(
        ["bash", "-lc", command],
        cwd=str(cwd),
        text=True,
        capture_output=True,
        timeout=timeout,
    )
    return CmdResult(["bash", "-lc", command], proc.returncode, proc.stdout, proc.stderr, time.monotonic() - started)


def json_dump(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def json_load(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def extract_json(text: str) -> Any | None:
    text = text.strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    fenced = re.search(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", text, re.S)
    if fenced:
        try:
            return json.loads(fenced.group(1))
        except Exception:
            pass
    # Conservative bracket scan.
    for opener, closer in (("[", "]"), ("{", "}")):
        start = text.find(opener)
        end = text.rfind(closer)
        if start >= 0 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except Exception:
                continue
    return None


def slug(text: str, limit: int = 40) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return (s or "task")[:limit]


def stable_id(*parts: str, length: int = 10) -> str:
    digest = hashlib.sha256("\x1f".join(parts).encode()).hexdigest()
    return digest[:length]


def which(name: str) -> str | None:
    from shutil import which as _which
    return _which(name)


def clip(text: str, limit: int = 12000) -> str:
    if len(text) <= limit:
        return text
    return text[: limit // 2] + "\n...<clipped>...\n" + text[-limit // 2 :]


def count_lines(paths: Iterable[Path]) -> int:
    total = 0
    for path in paths:
        try:
            total += len(path.read_text(encoding="utf-8", errors="ignore").splitlines())
        except OSError:
            continue
    return total
