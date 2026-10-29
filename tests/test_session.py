import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from worddrill.data import Word  # noqa: E402
from worddrill.session import DrillSession  # noqa: E402
from worddrill.srs import WordState, grade  # noqa: E402


def make_word(name: str) -> Word:
    return Word(key=f"b:{name}", book="b", word=name, ipa="/x/", pos="v.",
                cn="释义", en=f"I {name} it.", zh="例句。")


class Clock:
    def __init__(self, start: float = 1000.0) -> None:
        self.value = start

    def __call__(self) -> float:
        return self.value

    def tick(self, seconds: float) -> None:
        self.value += seconds


def test_typing_a_full_word_submits_automatically():
    clock = Clock()
    session = DrillSession(words=[make_word("cache")], mode="follow", now=clock)
    for char in "cach":
        assert session.type_char(char) is False
        assert session.phase == "typing"
    assert session.type_char("e") is True
    assert session.phase == "result"
    assert session.last_answer is not None
    assert session.last_answer.correct is True
    assert session.last_answer.quality == 4


def test_wrong_word_waits_for_enter_and_scores_zero():
    clock = Clock()
    session = DrillSession(words=[make_word("cache")], mode="dictation", now=clock)
    for char in "cachx":
        session.type_char(char)
    assert session.phase == "typing"
    answer = session.submit()
    assert answer is not None and answer.correct is False
    assert answer.quality == 0
    assert answer.typed == "cachx"


def test_hint_fills_a_prefix_and_caps_quality():
    session = DrillSession(words=[make_word("deploy")], mode="spelling",
                          now=Clock())
    assert session.hint() == "d"
    assert session.typed == "d"
    assert session.hint() == "e"
    assert session.typed == "de"
    assert session.reveal() == "deploy"
    answer = session.submit()
    assert answer is not None
    assert answer.correct is True
    assert answer.hints == len("deploy")
    assert answer.quality == 3


def test_hint_stops_at_end_of_word():
    session = DrillSession(words=[make_word("go")], mode="spelling", now=Clock())
    assert session.hint() == "g"
    assert session.hint() == "o"
    assert session.hint() is None


def test_backspace_and_clear():
    session = DrillSession(words=[make_word("cache")], mode="follow", now=Clock())
    session.type_char("c")
    session.type_char("a")
    session.backspace()
    assert session.typed == "c"
    session.clear_typed()
    assert session.typed == ""


def test_advance_walks_through_words_and_finishes():
    clock = Clock()
    session = DrillSession(words=[make_word("a"), make_word("b")], mode="follow",
                           now=clock)
    assert session.index == 0
    for char in "a":
        session.type_char(char)
    assert session.advance() is True
    assert session.index == 1 and session.phase == "typing"
    for char in "b":
        session.type_char(char)
    assert session.advance() is False
    assert session.phase == "done"
    result = session.result()
    assert result.total == 2 and result.correct == 2
    assert result.accuracy == 1.0


def test_skip_records_a_miss_and_feeds_review():
    session = DrillSession(words=[make_word("cache")], mode="dictation",
                          now=Clock())
    answer = session.skip()
    assert answer is not None and answer.skipped and not answer.correct


def test_selfcheck_uses_quality_grades():
    session = DrillSession(words=[make_word("cache")], mode="selfcheck",
                          now=Clock())
    assert session.type_char("c") is False, "selfcheck does not accept typing"
    answer = session.self_grade(1)
    assert answer is not None
    assert answer.self_graded and answer.correct is False
    assert answer.quality == 1


def test_on_answer_callback_receives_graded_state():
    seen = []
    session = DrillSession(words=[make_word("cache")], mode="follow", now=Clock())

    def callback(word, state, answer, correct):
        grade(state, answer.quality, now=0)
        seen.append((word.word, correct, state.status, state.correct))

    session.on_answer = callback
    for char in "cache":
        session.type_char(char)
    assert seen == [("cache", True, "learning", 1)]


def test_unknown_mode_is_rejected():
    with pytest.raises(ValueError):
        DrillSession(words=[make_word("a")], mode="nonsense")


def test_empty_session_is_done_immediately():
    session = DrillSession(words=[], mode="smart", now=Clock())
    assert session.phase == "done"
    assert session.current is None
    assert session.result().total == 0


def test_prompt_variant_mixes_follow_and_masked_cards():
    word = make_word("cache")
    session = DrillSession(words=[word], mode="smart", now=Clock())
    session.states[word.key] = WordState()
    assert session.prompt_variant() == "follow", "unseen words are shown first"
    session.states[word.key] = WordState(status="review", reps=3, wrong=0)
    assert session.prompt_variant() == "dictation", "seen words are masked"


def test_timing_is_tracked_per_word():
    clock = Clock()
    session = DrillSession(words=[make_word("cache")], mode="follow", now=clock)
    clock.tick(4.5)
    for char in "cache":
        session.type_char(char)
    assert session.last_answer is not None
    assert session.last_answer.seconds == pytest.approx(4.5)
    assert session.elapsed == pytest.approx(4.5)