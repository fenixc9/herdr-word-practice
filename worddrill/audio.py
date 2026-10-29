"""Optional pronunciation via whichever local speech tool exists.

Two accents are supported because they are worth learning separately: a word can
be perfectly familiar in one and unfamiliar in the other. Not every backend can
switch voice, so accents degrade to "whatever this engine does" rather than
failing.
"""

from __future__ import annotations

import os
import shutil
import subprocess

from .data import Word

ACCENTS = ("us", "uk")

# (binary, argv for US, argv for UK). ``None`` means "this engine cannot switch".
CANDIDATES: tuple[tuple[str, list[str] | None, list[str] | None], ...] = (
    ("espeak-ng",
     ["espeak-ng", "-v", "en-us", "-s", "150"],
     ["espeak-ng", "-v", "en-gb", "-s", "150"]),
    ("espeak",
     ["espeak", "-v", "en-us", "-s", "150"],
     ["espeak", "-v", "en-gb", "-s", "150"]),
    ("say",
     ["say", "-r", "170", "-v", "Samantha"],
     ["say", "-r", "170", "-v", "Daniel"]),
    ("spd-say", ["spd-say", "-w", "-l", "en-US"], ["spd-say", "-w", "-l", "en-GB"]),
)


def _pick(entry: tuple[str, list[str] | None, list[str] | None],
          accent: str) -> list[str]:
    _, american, british = entry
    chosen = british if accent == "uk" else american
    if chosen is None:
        chosen = american or british or [entry[0]]
    return list(chosen)


def find_provider(accent: str = "us") -> list[str] | None:
    override = os.environ.get("WORDDRILL_SAY")
    if override:
        return override.split()
    if os.environ.get("WORDDRILL_NO_AUDIO"):
        return None
    for entry in CANDIDATES:
        if shutil.which(entry[0]):
            return _pick(entry, accent)
    return None


def describe_provider(accent: str | None = None) -> str:
    provider = find_provider(accent or "us")
    return provider[0] if provider else "none"


def pronounce(word: Word, *, provider: list[str] | None = None,
              accent: str = "us") -> bool:
    """Fire and forget: audio must never block or break the drill."""
    argv = provider if provider is not None else find_provider(accent)
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