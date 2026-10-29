"""Talking to Herdr: notifications, pane launches, context, and nudges."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

PLUGIN_ID = "herdr-word-practice"


def herdr_bin() -> str:
    return os.environ.get("HERDR_BIN_PATH") or shutil.which("herdr") or "herdr"


def in_herdr() -> bool:
    return os.environ.get("HERDR_ENV") == "1"


def run_herdr(args: list[str], *, timeout: float = 5.0) -> dict | None:
    """Run a herdr CLI call and return the JSON result, or None on failure."""
    result = run_herdr_raw(args, timeout=timeout)
    if result is None:
        return None
    if isinstance(result.get("error"), dict):
        return None
    payload = result.get("result") if isinstance(result.get("result"), dict) else result
    return payload if isinstance(payload, dict) else {"raw": payload}


def run_herdr_raw(args: list[str], *, timeout: float = 5.0) -> dict | None:
    """Like :func:`run_herdr`, but also returns ``error`` payloads."""
    if not in_herdr() and not os.environ.get("HERDR_BIN_PATH"):
        return None
    try:
        proc = subprocess.run(
            [herdr_bin(), *args], capture_output=True, text=True, timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    # herdr writes success JSON to stdout and error JSON to stderr.
    text = proc.stdout.strip() or proc.stderr.strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"raw": text, "returncode": proc.returncode}


def notify(title: str, body: str = "", *, sound: str = "none",
           timeout: float = 4.0) -> bool:
    args = ["notification", "show", title]
    if body:
        args += ["--body", body]
    if sound and sound != "none":
        args += ["--sound", sound]
    return run_herdr(args, timeout=timeout) is not None


def open_pane(entrypoint: str, *, placement: str | None = None,
              env: dict[str, str] | None = None, focus: bool = True,
              timeout: float = 8.0) -> dict | None:
    args = ["plugin", "pane", "open", "--plugin", PLUGIN_ID, "--entrypoint", entrypoint]
    if placement:
        args += ["--placement", placement]
    for key, value in (env or {}).items():
        args += ["--env", f"{key}={value}"]
    args.append("--focus" if focus else "--no-focus")
    return run_herdr(args, timeout=timeout)


def open_pane_detailed(entrypoint: str, *, placement: str | None = None,
                       env: dict[str, str] | None = None, focus: bool = True,
                       timeout: float = 8.0) -> tuple[dict | None, str | None]:
    """Open a pane and report *why* it failed, if it did.

    ``ui_busy`` is special: it only means a popup is already on screen, which is
    exactly the state the caller wanted, so the caller can treat it as success.
    """
    args = ["plugin", "pane", "open", "--plugin", PLUGIN_ID, "--entrypoint", entrypoint]
    if placement:
        args += ["--placement", placement]
    for key, value in (env or {}).items():
        args += ["--env", f"{key}={value}"]
    args.append("--focus" if focus else "--no-focus")
    raw = run_herdr_raw(args, timeout=timeout)
    if raw is None:
        return None, "herdr did not answer"
    error = raw.get("error")
    if isinstance(error, dict):
        return None, str(error.get("code") or error.get("message") or "error")
    return raw, None


def plugin_root() -> Path:
    env = os.environ.get("HERDR_PLUGIN_ROOT")
    return Path(env) if env else Path(__file__).resolve().parent.parent


def _env_json(name: str) -> dict:
    raw = os.environ.get(name)
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def context() -> dict:
    return _env_json("HERDR_PLUGIN_CONTEXT_JSON")


def event_payload() -> dict:
    return _env_json("HERDR_PLUGIN_EVENT_JSON")


def find_status(payload: object, depth: int = 0) -> str | None:
    """Find an agent status in an event payload without assuming one shape."""
    if depth > 6:
        return None
    if isinstance(payload, dict):
        for key in ("agent_status", "status", "state"):
            value = payload.get(key)
            if isinstance(value, str) and value.lower() in {
                "idle", "working", "blocked", "done", "unknown",
            }:
                return value.lower()
        for value in payload.values():
            found = find_status(value, depth + 1)
            if found:
                return found
    elif isinstance(payload, list):
        for item in payload:
            found = find_status(item, depth + 1)
            if found:
                return found
    return None


def should_nudge(status: str | None, last_nudge: float, now: float,
                 min_gap_minutes: int, quiet_hours: tuple[int, int]) -> tuple[bool, str]:
    if status not in {"done", "idle"}:
        return False, f"status {status!r} is not idle/done"
    gap = now - last_nudge
    if last_nudge and gap < min_gap_minutes * 60:
        remaining = int(min_gap_minutes - gap / 60)
        return False, f"throttled for another {max(1, remaining)} min"
    hour = __import__("time").localtime(now).tm_hour
    start, end = quiet_hours
    quiet = start <= hour < end if start <= end else hour >= start or hour < end
    if quiet:
        return False, "quiet hours"
    return True, "ok"


def load_json(path: Path, default: object) -> object:
    try:
        with Path(path).open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        return default


def save_json(path: Path, data: object) -> None:
    from .store import atomic_write_json

    atomic_write_json(Path(path), data)


def stderr(message: str) -> None:
    sys.stderr.write(message.rstrip() + "\n")
    sys.stderr.flush()
