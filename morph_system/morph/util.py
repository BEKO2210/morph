from __future__ import annotations

import hashlib
import json
import os
import queue
import re
import shlex
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable


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


_STREAM_EOF = object()


def run_streamed(
    command: list[str] | str,
    *,
    cwd: Path,
    timeout: int = 900,
    env: dict[str, str] | None = None,
    log_path: Path | None = None,
    echo: bool = False,
    heartbeat_s: float = 20.0,
    on_heartbeat: Callable[[int], None] | None = None,
) -> CmdResult:
    """Run a command with stdout+stderr streamed live instead of buffered
    until exit. Output is teed to ``log_path`` (if given) line by line as it
    arrives, so a killed/crashed process still leaves a readable partial log.
    ``on_heartbeat`` fires periodically while the process is silent, so
    long-running agent calls stay visible instead of looking hung.
    """
    args = shlex.split(command) if isinstance(command, str) else command
    started = time.monotonic()
    proc = subprocess.Popen(
        args,
        cwd=str(cwd),
        env={**os.environ, **(env or {})},
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    q: "queue.Queue" = queue.Queue()

    def _pump() -> None:
        try:
            for line in iter(proc.stdout.readline, ""):
                q.put(line)
        finally:
            q.put(_STREAM_EOF)

    pump = threading.Thread(target=_pump, daemon=True)
    pump.start()

    lines: list[str] = []
    log_fh = None
    if log_path:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_fh = open(log_path, "w", encoding="utf-8")
    try:
        while True:
            elapsed = time.monotonic() - started
            if timeout and elapsed > timeout:
                proc.kill()
                proc.wait()
                raise subprocess.TimeoutExpired(args, timeout)
            wait_for = heartbeat_s
            if timeout:
                wait_for = max(0.1, min(heartbeat_s, timeout - elapsed))
            try:
                item = q.get(timeout=wait_for)
            except queue.Empty:
                if on_heartbeat:
                    on_heartbeat(int(elapsed))
                continue
            if item is _STREAM_EOF:
                break
            lines.append(item)
            if log_fh:
                log_fh.write(item)
                log_fh.flush()
            if echo:
                # stdout is reserved for MORPH's final JSON result; raw
                # agent/check output goes to stderr like [MORPH] progress.
                print(item, end="", file=sys.stderr, flush=True)
        proc.wait(timeout=max(1, int(timeout)) if timeout else None)
    finally:
        if log_fh:
            log_fh.close()
        if proc.stdout:
            proc.stdout.close()
        pump.join(timeout=1)
    stdout_text = "".join(lines)
    return CmdResult(args, proc.returncode, stdout_text, "", time.monotonic() - started)


_TRANSIENT_ERROR_RE = re.compile(
    r"(?i)("
    r"websocket|connection reset|bad gateway|gateway time-?out|\b50[234]\b|"
    r"stream disconnected|econnreset|etimedout|temporarily unavailable|"
    r"network is unreachable|timed out|socket hang up|connection refused|"
    r"failed to connect|dns lookup failed|tls handshake"
    r")"
)


def is_transient_error(text: str) -> bool:
    """Best-effort detection of transient transport failures (dropped
    websocket, reset connection, 5xx, etc.) worth retrying — as opposed to
    normal agent/task failures, which must never be silently retried."""
    return bool(_TRANSIENT_ERROR_RE.search(text or ""))


def run_agent(
    command: list[str] | str,
    *,
    cwd: Path,
    timeout: int = 900,
    env: dict[str, str] | None = None,
    log_path: Path | None = None,
    echo: bool = False,
    label: str = "agent",
    report: Callable[[str], None] | None = None,
    retries: int = 2,
    backoff_s: float = 5.0,
    heartbeat_s: float = 20.0,
) -> CmdResult:
    """Streamed subprocess execution with bounded retry-with-backoff, but
    only for clearly transient transport errors. Normal non-zero exits
    (agent declined, bad prompt, real bug) are returned as-is on the first
    attempt so callers can treat them as real failures."""
    wait = backoff_s
    attempt = 0
    while True:
        def _heartbeat(elapsed: int, _label=label) -> None:
            if report:
                report(f"{_label} still running ({elapsed}s elapsed)")

        result = run_streamed(
            command, cwd=cwd, timeout=timeout, env=env, log_path=log_path,
            echo=echo, heartbeat_s=heartbeat_s, on_heartbeat=_heartbeat,
        )
        if result.returncode == 0 or attempt >= retries or not is_transient_error(result.stdout):
            return result
        attempt += 1
        if report:
            report(f"{label} hit a transient error, retrying in {int(wait)}s (attempt {attempt}/{retries})")
        time.sleep(wait)
        wait *= 2


def filter_ignored_status(status_text: str, ignore_paths: Iterable[str]) -> list[str]:
    """Drop `git status --porcelain` lines that only touch MORPH's own
    install/runtime artifacts (per ``ignore_paths``), so MORPH never treats
    its own untracked files as a dirty project working tree."""
    ignore_paths = list(ignore_paths)
    dirty = []
    for line in status_text.splitlines():
        if not line.strip():
            continue
        path = line[3:] if len(line) >= 4 else line
        # Rename records can look like "old -> new"; compare both ends.
        paths = [x.strip() for x in path.split(" -> ")]
        def is_ignored(candidate: str) -> bool:
            return any(
                candidate.startswith(ignored)
                if ignored.endswith("/")
                else candidate == ignored
                for ignored in ignore_paths
            )

        if ignore_paths and all(is_ignored(x) for x in paths):
            continue
        dirty.append(line)
    return dirty


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
