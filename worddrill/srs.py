"""Spaced-repetition scheduling and session planning.

A compact SM-2 variant tuned for short, interruptible drills: new words come
back after ten minutes, then a day, then grow by ease; lapses fall back into
the learning queue; mastered words stop appearing in smart sessions.
"""

from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass
from typing import Iterable, Sequence

from .data import Word

MINUTE = 60.0
DAY = 86400.0
LEARNING_STEP = 10 * MINUTE
SECOND_STEP = 1 * DAY
MASTERED_INTERVAL_DAYS = 21.0
MAX_INTERVAL_DAYS = 365.0 * 2

STATUS_NEW = "new"
STATUS_LEARNING = "learning"
STATUS_REVIEW = "review"
STATUS_MASTERED = "mastered"

MODES = ("smart", "free", "follow", "dictation", "spelling", "selfcheck", "review")

MODE_LABELS = {
    "smart": "智能复习",
    "free": "自由练习",
    "follow": "跟打",
    "dictation": "默写",
    "spelling": "看中文拼写",
    "selfcheck": "自测",
    "review": "错词本",
}

MODE_HINTS = {
    "smart": "按记忆曲线挑词：该复习的先来，再补一点新词。",
    "free": "不按记忆曲线排，随便挑词练——想练哪本、练多少都行。",
    "follow": "看着单词打一遍，先建立手感和拼写记忆。",
    "dictation": "只看中文和挖空例句，把单词默写出来。",
    "spelling": "只给中文释义，凭记忆拼出英文。",
    "selfcheck": "看见单词先自问：认识、模糊，还是完全不认识。",
    "review": "只练之前拼错过的词。",
}


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


@dataclass
class WordState:
    reps: int = 0
    lapses: int = 0
    ease: float = 2.5
    interval: float = 0.0
    due: float = 0.0
    last: float = 0.0
    first_seen: float = 0.0
    status: str = STATUS_NEW
    correct: int = 0
    wrong: int = 0
    hint_used: int = 0
    streak: int = 0

    @classmethod
    def from_dict(cls, raw: dict) -> "WordState":
        state = cls()
        if not isinstance(raw, dict):
            return state
        state.reps = int(raw.get("reps", 0) or 0)
        state.lapses = int(raw.get("lapses", 0) or 0)
        state.ease = float(raw.get("ease", 2.5) or 2.5)
        state.interval = float(raw.get("interval", 0.0) or 0.0)
        state.due = float(raw.get("due", 0.0) or 0.0)
        state.last = float(raw.get("last", 0.0) or 0.0)
        state.first_seen = float(raw.get("first_seen", 0.0) or 0.0)
        status = str(raw.get("status", STATUS_NEW) or STATUS_NEW)
        state.status = status if status in {
            STATUS_NEW, STATUS_LEARNING, STATUS_REVIEW, STATUS_MASTERED,
        } else STATUS_NEW
        state.correct = int(raw.get("correct", 0) or 0)
        state.wrong = int(raw.get("wrong", 0) or 0)
        state.hint_used = int(raw.get("hint_used", 0) or 0)
        state.streak = int(raw.get("streak", 0) or 0)
        return state

    def to_dict(self) -> dict:
        return {
            "reps": self.reps, "lapses": self.lapses,
            "ease": round(self.ease, 3), "interval": round(self.interval, 3),
            "due": round(self.due, 3), "last": round(self.last, 3),
            "first_seen": round(self.first_seen, 3), "status": self.status,
            "correct": self.correct, "wrong": self.wrong,
            "hint_used": self.hint_used, "streak": self.streak,
        }

    @property
    def accuracy(self) -> float:
        total = self.correct + self.wrong
        return self.correct / total if total else 0.0

    @property
    def interval_days(self) -> float:
        return self.interval / DAY

    def is_due(self, now: float) -> bool:
        return self.status in {STATUS_LEARNING, STATUS_REVIEW} and self.due <= now

    def is_weak(self) -> bool:
        return self.wrong > 0 and self.status != STATUS_MASTERED


def grade(state: WordState, quality: int, now: float | None = None,
          hinted: bool = False) -> WordState:
    """Apply an SM-2 style update. ``quality`` is 0..5, >=3 means recalled."""
    now = time.time() if now is None else now
    quality = int(clamp(quality, 0, 5))
    if state.first_seen <= 0:
        state.first_seen = now
    state.last = now
    if hinted and quality >= 3:
        quality = min(quality, 3)

    if quality < 3:
        state.lapses += 1
        state.wrong += 1
        state.streak = 0
        state.reps = 0
        state.ease = clamp(state.ease - 0.2, 1.3, 2.8)
        state.interval = LEARNING_STEP
        state.due = now + LEARNING_STEP
        state.status = STATUS_LEARNING
        return state

    state.correct += 1
    state.streak += 1
    state.reps += 1
    state.ease = clamp(state.ease + (0.1 - (5 - quality) * 0.08), 1.3, 2.8)

    if state.reps == 1:
        state.interval = LEARNING_STEP
        state.status = STATUS_LEARNING
    elif state.reps == 2:
        state.interval = SECOND_STEP
        state.status = STATUS_REVIEW
    else:
        growth = state.ease if quality >= 4 else max(1.2, state.ease - 0.15)
        days = min(max(1.0, state.interval_days * growth), MAX_INTERVAL_DAYS)
        state.interval = days * DAY
        state.status = STATUS_REVIEW

    if state.interval_days >= MASTERED_INTERVAL_DAYS and state.reps >= 4:
        state.status = STATUS_MASTERED
    state.due = now + state.interval
    return state


def mark_mastered(state: WordState, now: float | None = None) -> WordState:
    now = time.time() if now is None else now
    state.status = STATUS_MASTERED
    state.reps = max(state.reps, 4)
    state.interval = max(state.interval, MASTERED_INTERVAL_DAYS * DAY)
    state.due = now + state.interval
    state.last = now
    return state


@dataclass
class PlanRequest:
    words: Sequence[Word]
    states: dict[str, WordState]
    mode: str = "smart"
    size: int = 10
    now: float | None = None
    daily_new_limit: int = 8
    new_today: int = 0
    seed: int | None = None


def plan_session(request: PlanRequest) -> list[Word]:
    """Pick the words for one session. Deterministic for a given seed."""
    now = time.time() if request.now is None else request.now
    rng = random.Random(request.seed)
    size = max(1, int(request.size))
    states = request.states
    mode = request.mode

    def state_of(word: Word) -> WordState:
        return states.get(word.key) or WordState()

    candidates = list(request.words)

    if mode == "free":
        # No schedule, no budgets: a random handful of this book, nothing more.
        pool = list(candidates)
        rng.shuffle(pool)
        return pool[:size]

    if mode == "review":
        weak = [w for w in candidates if state_of(w).is_weak()]
        weak.sort(key=lambda w: (state_of(w).status == STATUS_MASTERED,
                                 -state_of(w).wrong, state_of(w).last))
        if len(weak) < size:
            extras = [w for w in candidates if state_of(w).status == STATUS_NEW]
            rng.shuffle(extras)
            weak.extend(extras[: size - len(weak)])
        return weak[:size]

    if mode in {"follow", "dictation", "spelling"}:
        pool = [w for w in candidates if state_of(w).status != STATUS_MASTERED]
        if not pool:
            pool = list(candidates)
        pool.sort(key=lambda w: (state_of(w).status != STATUS_NEW,
                                 state_of(w).wrong == 0, rng.random()))
        return pool[:size]

    if mode == "selfcheck":
        due = [w for w in candidates if state_of(w).status != STATUS_NEW]
        rng.shuffle(due)
        fresh = [w for w in candidates if state_of(w).status == STATUS_NEW]
        rng.shuffle(fresh)
        return (due + fresh)[:size]

    # smart mode: due reviews first, then unseen words, and only then the words
    # that are still on a learning step but not due yet. Putting "learning" ahead
    # of "new" made a second round right after the first repeat the same cards:
    # everything you just answered sits in `learning` until its step comes up.
    due_words = [w for w in candidates if state_of(w).is_due(now)]
    due_words.sort(key=lambda w: (state_of(w).due, -state_of(w).wrong))
    later = [w for w in candidates
             if not state_of(w).is_due(now)
             and state_of(w).status in {STATUS_LEARNING, STATUS_REVIEW}]
    later.sort(key=lambda w: state_of(w).due)
    weak_words = [w for w in candidates if state_of(w).is_weak() and w not in due_words]
    weak_words.sort(key=lambda w: (-state_of(w).wrong, state_of(w).last))
    new_words = [w for w in candidates if state_of(w).status == STATUS_NEW]
    rng.shuffle(new_words)

    allowance = max(0, request.daily_new_limit - request.new_today)
    if due_words:
        # Mix reviews with a slice of new words, and respect the daily cap.
        new_budget = min(max(1 if size >= 4 else 0, int(round(size * 0.4))),
                         allowance)
    else:
        # Nothing is due, so the whole round should be new material. The daily
        # cap is a soft target for the first round of the day; it must not turn
        # "again" into a repeat of the cards you just answered.
        new_budget = size

    picked: list[Word] = []
    seen: set[str] = set()

    def add(items: Iterable[Word], limit: int | None = None) -> None:
        added = 0
        for word in items:
            if len(picked) >= size:
                return
            if limit is not None and added >= limit:
                return
            if word.key in seen:
                continue
            seen.add(word.key)
            picked.append(word)
            added += 1

    add(due_words)
    add(new_words, limit=new_budget)
    add(weak_words)
    # Fill the rest of the round with cards that are not due yet, but only after
    # the genuinely new material above.
    add(later)
    if len(picked) < size:
        add(new_words)
    if len(picked) < size:
        rest = [w for w in candidates if w not in picked]
        rng.shuffle(rest)
        add(rest)
    return picked[:size]


def due_count(words: Sequence[Word], states: dict[str, WordState],
              now: float | None = None) -> int:
    now = time.time() if now is None else now
    return sum(1 for w in words if (states.get(w.key) or WordState()).is_due(now))


def status_counts(words: Sequence[Word], states: dict[str, WordState]) -> dict[str, int]:
    counts = {STATUS_NEW: 0, STATUS_LEARNING: 0, STATUS_REVIEW: 0, STATUS_MASTERED: 0}
    for word in words:
        status = (states.get(word.key) or WordState()).status
        counts[status] = counts.get(status, 0) + 1
    return counts


def local_streak(days: dict[str, dict], today: str) -> int:
    """Count consecutive days ending today with at least one answer."""
    from datetime import date, timedelta

    try:
        year, month, day = (int(part) for part in today.split("-"))
        current = date(year, month, day)
    except (ValueError, AttributeError):
        return 0
    streak = 0
    while True:
        entry = days.get(current.isoformat())
        if not entry or int(entry.get("correct", 0)) + int(entry.get("wrong", 0)) <= 0:
            break
        streak += 1
        current -= timedelta(days=1)
    return streak


def next_due_label(states: dict[str, WordState], now: float | None = None) -> str:
    now = time.time() if now is None else now
    dues = [state.due for state in states.values() if state.due > 0]
    if not dues:
        return "—"
    soonest = min(dues)
    delta = soonest - now
    if delta <= 0:
        return "现在"
    if delta < 3600:
        return f"{int(delta / 60) + 1} 分钟后"
    if delta < 86400:
        return f"{int(delta / 3600) + 1} 小时后"
    return f"{int(delta / 86400) + 1} 天后"


def start_of_day(now: float) -> float:
    return math.floor(now / DAY) * DAY
