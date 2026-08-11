from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Callable, TextIO

# Pure ANSI escape codes on purpose — MORPH has zero Python dependencies,
# so no rich/colorama here. Every terminal MORPH is realistically run in
# (Claude Code, Codex CLI, any modern shell) understands these.
_RESET = "\033[0m"
_BOLD = "\033[1m"
_DIM = "\033[2m"
_COLORS = {
    "cyan": "\033[36m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "red": "\033[31m",
    "blue": "\033[34m",
}
_ANSI_RE = re.compile(r"\033\[[0-9;]*m")
_SPINNER_FRAMES = "|/-\\"


def supports_color(stream: TextIO = sys.stderr) -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("MORPH_FORCE_COLOR"):
        return True
    if os.environ.get("MORPH_NO_COLOR"):
        return False
    try:
        return stream.isatty()
    except Exception:
        return False


def strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


def classify(msg: str) -> str:
    """Best-effort color for a [MORPH] progress line, based on its own
    wording — no separate level parameter to thread through every call
    site, so existing report(...) calls need no changes."""
    low = msg.lower()
    # Checked first: a transient-error retry is still in progress, not a
    # final failure, even though its own text contains "error".
    if "still running" in low or "retrying" in low or "transient" in low:
        return "yellow"
    if "failed" in low or "error" in low or "could not" in low:
        return "red"
    if any(kw in low for kw in ("completed", "applied", "passed", "cleaning")):
        return "green"
    if "started" in low or "running " in low:
        return "blue"
    return "cyan"


def _colorize(text: str, color: str) -> str:
    return f"{_COLORS[color]}{text}{_RESET}"


def make_reporter(run_dir: Path, *, stream: TextIO = sys.stderr) -> Callable[[str], None]:
    """Build a report(msg) callable: always appends a plain-text line to
    run_dir/progress.log, and prints a live status line to `stream`.
    When `stream` is a real terminal, output is colorized by message kind
    and heartbeat ("... still running (Ns elapsed)") lines animate a small
    spinner in place instead of piling up one line per tick. Falls back to
    plain, newline-per-message text when not a TTY (piped, redirected, CI)
    so scripted/logged output stays exactly as readable as before."""
    log_path = run_dir / "progress.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    color = supports_color(stream)
    state = {"spin": 0, "on_spinner_line": False}

    def report(msg: str) -> None:
        with open(log_path, "a", encoding="utf-8") as fh:
            fh.write(f"[MORPH] {strip_ansi(msg)}\n")

        if not color:
            print(f"[MORPH] {msg}", file=stream, flush=True)
            return

        prefix = _colorize("[MORPH]", "cyan")
        is_heartbeat = "still running" in msg.lower()
        if is_heartbeat:
            frame = _SPINNER_FRAMES[state["spin"] % len(_SPINNER_FRAMES)]
            state["spin"] += 1
            line = f"\r{prefix} {_colorize(frame, 'yellow')} {_DIM}{msg}{_RESET}"
            print(line + " " * 8, end="", file=stream, flush=True)
            state["on_spinner_line"] = True
            return

        if state["on_spinner_line"]:
            print(file=stream)  # move off the spinner line before a normal one
            state["on_spinner_line"] = False
        body = _colorize(msg, classify(msg))
        print(f"{prefix} {body}", file=stream, flush=True)

    return report
