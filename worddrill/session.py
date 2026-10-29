"""Session state machine: typing, hints, grading, and self-test flow."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Sequence

from .data import Word
from .srs import MODES, WordState


@dataclass
class Answer:
    word: Word
    quality: int
    correct: bool
    typed: str
    hints: int
    seconds: float
    self_graded: bool = False
    skipped: bool = False


@dataclass
class SessionResult:
    answers: list[Answer]
    elapsed: float
    mode: str
    book_label: str

    @property
    def total(self) -> int:
        return len(self.answers)

    @property
    def correct(self) -> int:
        return sum(1 for a in self.answers if a.correct)

    @property
    def wrong(self) -> int:
        return self.total - self.correct

    @property
    def accuracy(self) -> float:
        return self.correct / self.total if self.total else 0.0

    @property
    def words_per_minute(self) -> float:
        return self.total / (self.elapsed / 60.0) if self.elapsed > 0 else 0.0

    @property
    def wrong_words(self) -> list[str]:
        return [a.word.word for a in self.answers if not a.correct]


@dataclass
class DrillSession:
    words: Sequence[Word]
    mode: str
    book_label: str = ""
    now: Callable[[], float] = time.time
    on_answer: Callable[[Word, WordState, Answer, bool], None] | None = None
    states: dict[str, WordState] = field(default_factory=dict)

    index: int = 0
    typed: str = ""
    hints: int = 0
    phase: str = "typing"  # typing | result | done
    last_answer: Answer | None = None
    answers: list[Answer] = field(default_factory=list)
    started: float = 0.0
    word_started: float = 0.0

    def __post_init__(self) -> None:
        if self.mode not in MODES:
            raise ValueError(f"unknown mode '{self.mode}'")
        self.started = self.now()
        self.word_started = self.started
        if not self.words:
            self.phase = "done"

    @property
    def current(self) -> Word | None:
        if 0 <= self.index < len(self.words):
            return self.words[self.index]
        return None

    @property
    def total(self) -> int:
        return len(self.words)

    @property
    def typed_mode(self) -> bool:
        return self.mode != "selfcheck"

    @property
    def progress(self) -> float:
        return self.index / self.total if self.total else 1.0

    @property
    def elapsed(self) -> float:
        return max(0.0, self.now() - self.started)

    def state_of(self, word: Word) -> WordState:
        if word.key not in self.states:
            self.states[word.key] = WordState()
        return self.states[word.key]

    # -- typing ----------------------------------------------------------
    def type_char(self, char: str) -> bool:
        if self.phase != "typing" or not self.typed_mode:
            return False
        if len(char) != 1 or char in "\r\n\t":
            return False
        self.typed += char
        word = self.current
        if word is None:
            return False
        if self.typed == word.word:
            self.submit()
            return True
        return False

    def backspace(self) -> None:
        if self.phase == "typing":
            self.typed = self.typed[:-1]

    def clear_typed(self) -> None:
        self.typed = ""

    def hint(self) -> str | None:
        word = self.current
        if word is None or self.phase != "typing":
            return None
        if self.hints >= len(word.word):
            return None
        self.hints += 1
        prefix = word.word[: self.hints]
        if not self.typed.startswith(prefix):
            self.typed = prefix
        return word.word[self.hints - 1]

    def reveal(self) -> str:
        word = self.current
        if word is None:
            return ""
        self.hints = len(word.word)
        self.typed = word.word
        return word.word

    # -- grading ---------------------------------------------------------
    def submit(self, skipped: bool = False) -> Answer | None:
        if self.phase != "typing":
            return None
        word = self.current
        if word is None:
            return None
        typed = self.typed.strip()
        correct = (not skipped) and typed.lower() == word.word.lower()
        if skipped:
            quality = 0
        elif correct:
            quality = 3 if self.hints else 4
        else:
            quality = 0
        answer = Answer(
            word=word, quality=quality, correct=correct, typed=typed,
            hints=self.hints, seconds=max(0.0, self.now() - self.word_started),
            skipped=skipped,
        )
        self._finish_answer(answer, typed)
        return answer

    def self_grade(self, quality: int) -> Answer | None:
        if self.phase != "typing" or self.mode != "selfcheck":
            return None
        word = self.current
        if word is None:
            return None
        quality = max(0, min(5, int(quality)))
        answer = Answer(
            word=word, quality=quality, correct=quality >= 3, typed="",
            hints=0, seconds=max(0.0, self.now() - self.word_started),
            self_graded=True,
        )
        self._finish_answer(answer, "")
        return answer

    def _finish_answer(self, answer: Answer, typed: str) -> None:
        self.answers.append(answer)
        self.last_answer = answer
        if self.on_answer is not None:
            self.on_answer(answer.word, self.state_of(answer.word), answer,
                           answer.correct)
        self.phase = "result"
        self.typed = typed

    def advance(self) -> bool:
        if self.phase not in {"result", "typing"}:
            return False
        self.index += 1
        self.typed = ""
        self.hints = 0
        self.last_answer = None
        self.word_started = self.now()
        if self.index >= self.total:
            self.phase = "done"
            return False
        self.phase = "typing"
        return True

    def skip(self) -> Answer | None:
        if self.phase != "typing":
            return None
        return self.submit(skipped=True)

    def result(self) -> SessionResult:
        return SessionResult(
            answers=list(self.answers), elapsed=self.elapsed,
            mode=self.mode, book_label=self.book_label,
        )

    def prompt_variant(self, word: Word | None = None) -> str:
        """How much of the card to reveal.

        ``smart`` mixes: unseen words show fully (spelling lesson), words in
        rotation are masked (recall work).
        """
        word = word or self.current
        if self.mode == "selfcheck":
            return "selfcheck"
        if self.mode in {"follow", "free"}:
            return "follow"
        if self.mode == "dictation":
            return "dictation"
        if self.mode == "spelling":
            return "spelling"
        if self.mode == "smart" and word is not None:
            state = self.state_of(word)
            if state.status == "new" and state.wrong == 0:
                return "follow"
        return "dictation"