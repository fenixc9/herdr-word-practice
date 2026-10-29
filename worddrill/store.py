"""Durable progress and settings storage (plain JSON, atomic writes, flock)."""

from __future__ import annotations

import contextlib
import fcntl
import json
import os
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

from .srs import STATUS_NEW, WordState

STATE_VERSION = 1


def default_state_dir() -> Path:
    env = os.environ.get("HERDR_PLUGIN_STATE_DIR")
    if env:
        return Path(env)
    xdg = os.environ.get("XDG_STATE_HOME")
    if xdg:
        return Path(xdg) / "herdr-words"
    return Path.home() / ".local" / "state" / "herdr-words"


def default_config_dir() -> Path:
    env = os.environ.get("HERDR_PLUGIN_CONFIG_DIR")
    if env:
        return Path(env)
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg) / "herdr-words"
    return Path.home() / ".config" / "herdr-words"


DEFAULT_SETTINGS: dict = {
    "book": "cet4",
    "mode": "smart",
    "session_size": 10,
    "daily_new_limit": 8,
    "daily_goal": 20,
    "sound": True,
    "accent": "us",
    "auto_pronounce": True,
    "notify_on_finish": True,
    "nudge": {
        "enabled": True,
        "min_gap_minutes": 45,
        "quiet_hours": [23, 8],
    },
}


def _merge_defaults(defaults: dict, raw: dict) -> dict:
    merged = dict(defaults)
    for key, value in raw.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_defaults(merged[key], value)
        else:
            merged[key] = value
    return merged


def atomic_write_json(path: Path, data: object) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=1, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    finally:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp_name)


_LOCK_DEPTH: dict[str, int] = {}


@contextlib.contextmanager
def file_lock(state_dir: Path) -> Iterator[None]:
    """Exclusive lock over one state directory.

    Reentrant inside a single process: ``flock`` locks belong to the open file
    description, so a nested call on a second descriptor would deadlock against
    ourselves. Keep a per-path depth counter and only touch the kernel lock on
    the outermost level.
    """
    state_dir = Path(state_dir)
    state_dir.mkdir(parents=True, exist_ok=True)
    key = str(state_dir.resolve())
    if _LOCK_DEPTH.get(key):
        _LOCK_DEPTH[key] += 1
        try:
            yield
        finally:
            _LOCK_DEPTH[key] -= 1
        return

    with (state_dir / ".lock").open("a+") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        _LOCK_DEPTH[key] = 1
        try:
            yield
        finally:
            _LOCK_DEPTH[key] = 0
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@dataclass
class Progress:
    path: Path
    data: dict = field(default_factory=dict)

    @classmethod
    def load(cls, state_dir: Path) -> "Progress":
        state_dir = Path(state_dir)
        state_dir.mkdir(parents=True, exist_ok=True)
        path = state_dir / "progress.json"
        raw: dict = {}
        if path.is_file():
            try:
                with path.open("r", encoding="utf-8") as handle:
                    loaded = json.load(handle)
                if isinstance(loaded, dict):
                    raw = loaded
            except (json.JSONDecodeError, OSError):
                damaged = path.with_name(f"progress.corrupt-{int(time.time())}.json")
                with contextlib.suppress(OSError):
                    path.replace(damaged)
                raw = {}
        data = {
            "version": STATE_VERSION,
            "words": raw.get("words") if isinstance(raw.get("words"), dict) else {},
            "days": raw.get("days") if isinstance(raw.get("days"), dict) else {},
            "meta": raw.get("meta") if isinstance(raw.get("meta"), dict) else {},
        }
        data["meta"].setdefault("created", time.time())
        return cls(path=path, data=data)

    # -- word states -----------------------------------------------------
    def word_state(self, key: str) -> WordState:
        return WordState.from_dict(self.data["words"].get(key, {}))

    def set_word_state(self, key: str, state: WordState) -> None:
        self.data["words"][key] = state.to_dict()

    def state_map(self) -> dict[str, WordState]:
        return {key: WordState.from_dict(raw) for key, raw in self.data["words"].items()}

    def reset(self) -> None:
        self.data = {
            "version": STATE_VERSION, "words": {}, "days": {},
            "meta": {"created": time.time()},
        }

    # -- daily bookkeeping ----------------------------------------------
    def day_key(self, now: float | None = None) -> str:
        now = time.time() if now is None else now
        return time.strftime("%Y-%m-%d", time.localtime(now))

    def day(self, now: float | None = None) -> dict:
        entry = self.data["days"].setdefault(self.day_key(now), {})
        entry.setdefault("correct", 0)
        entry.setdefault("wrong", 0)
        entry.setdefault("new", 0)
        entry.setdefault("seconds", 0.0)
        entry.setdefault("sessions", 0)
        return entry

    def new_today(self, now: float | None = None) -> int:
        return int(self.day(now).get("new", 0))

    def record_answer(self, key: str, correct: bool, elapsed: float,
                      was_new: bool, now: float | None = None) -> None:
        now = time.time() if now is None else now
        day = self.day(now)
        if correct:
            day["correct"] += 1
        else:
            day["wrong"] += 1
        day["seconds"] = round(float(day.get("seconds", 0.0)) + max(0.0, elapsed), 2)
        if was_new:
            day["new"] += 1
        self.data["meta"]["last_answer"] = now
        self.data["meta"]["last_word"] = key

    def record_session(self, now: float | None = None) -> None:
        self.day(now)["sessions"] += 1

    def last_days(self, count: int = 7, now: float | None = None) -> list[tuple[str, dict]]:
        now = time.time() if now is None else now
        result = []
        for offset in range(count - 1, -1, -1):
            key = self.day_key(now - offset * 86400)
            result.append((key, self.data["days"].get(key, {})))
        return result

    def totals(self) -> dict:
        correct = sum(int(d.get("correct", 0)) for d in self.data["days"].values())
        wrong = sum(int(d.get("wrong", 0)) for d in self.data["days"].values())
        seconds = sum(float(d.get("seconds", 0)) for d in self.data["days"].values())
        sessions = sum(int(d.get("sessions", 0)) for d in self.data["days"].values())
        return {
            "correct": correct, "wrong": wrong, "answers": correct + wrong,
            "seconds": seconds, "sessions": sessions,
            "accuracy": correct / (correct + wrong) if correct + wrong else 0.0,
        }

    # -- persistence -----------------------------------------------------
    def save(self) -> None:
        atomic_write_json(self.path, self.data)

    def update(self, key: str, state: WordState) -> None:
        self.set_word_state(key, state)


@dataclass
class Settings:
    path: Path
    data: dict = field(default_factory=dict)

    @classmethod
    def load(cls, config_dir: Path) -> "Settings":
        config_dir = Path(config_dir)
        config_dir.mkdir(parents=True, exist_ok=True)
        path = config_dir / "settings.json"
        raw: dict = {}
        if path.is_file():
            try:
                with path.open("r", encoding="utf-8") as handle:
                    loaded = json.load(handle)
                if isinstance(loaded, dict):
                    raw = loaded
            except (json.JSONDecodeError, OSError):
                raw = {}
        return cls(path=path, data=_merge_defaults(DEFAULT_SETTINGS, raw))

    def get(self, key: str, default=None):
        return self.data.get(key, default)

    def save(self) -> None:
        atomic_write_json(self.path, self.data)


def prune_words(progress: Progress, allowed_keys: set[str]) -> int:
    stale = [key for key in progress.data["words"] if key not in allowed_keys]
    for key in stale:
        del progress.data["words"][key]
    return len(stale)


__all__ = [
    "Progress", "Settings", "DEFAULT_SETTINGS", "atomic_write_json", "file_lock",
    "default_state_dir", "default_config_dir", "prune_words", "STATUS_NEW",
]