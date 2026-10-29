"""Optional pronunciation via whichever local speech tool exists."""

from __future__ import annotations

import os
import shutil
import subprocess

from .data import Word

CANDIDATES = (
    ("espeak-ng", ["espeak-ng", "-v", "en-us", "-s", "150"]),
    ("espeak", ["espeak", "-v", "en-us", "-s", "150"]),
    ("say", ["say", "-r", "170"]),
    ("spd-say", ["spd-say", "-w"]),
)


def find_provider() -> list[str] | None:
    override = os.environ.get("WORDDRILL_SAY")
    if override:
        return override.split()
    if os.environ.get("WORDDRILL_NO_AUDIO"):
        return None
    for binary, argv in CANDIDATES:
        if shutil.which(binary):
            return list(argv)
    return None


def describe_provider() -> str:
    provider = find_provider()
    return provider[0] if provider else "none"


def pronounce(word: Word, *, provider: list[str] | None = None) -> bool:
    """Fire and forget: audio must never block or break the drill."""
    argv = provider if provider is not None else find_provider()
    if not argv:
        return False
    try:
        subprocess.Popen(
            [*argv, word.word],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL, start_new_session=True,
        )
        return True
    except OSError:
        return False