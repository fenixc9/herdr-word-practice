import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from worddrill import srs  # noqa: E402
from worddrill.data import Word  # noqa: E402


def word(name: str, book: str = "b") -> Word:
    return Word(key=f"{book}:{name}", book=book, word=name, ipa="", pos="v.",
                cn="释义", en=f"I use {name} daily.", zh="例句。")


def test_first_correct_answer_schedules_learning_step():
    state = srs.WordState()
    now = 1_000_000.0
    srs.grade(state, 4, now=now)
    assert state.status == srs.STATUS_LEARNING
    assert state.due == pytest.approx(now + srs.LEARNING_STEP)
    assert state.correct == 1 and state.wrong == 0


def test_second_correct_answer_moves_to_review_after_a_day():
    state = srs.WordState()
    srs.grade(state, 4, now=0)
    srs.grade(state, 4, now=10)
    assert state.status == srs.STATUS_REVIEW
    assert state.due == pytest.approx(10 + srs.SECOND_STEP)


def test_intervals_grow_and_word_becomes_mastered():
    state = srs.WordState()
    now = 0.0
    intervals = []
    for _ in range(6):
        srs.grade(state, 5, now=now)
        intervals.append(state.interval_days)
        now = state.due
    assert intervals == sorted(intervals), "intervals must grow monotonically"
    assert state.status == srs.STATUS_MASTERED


def test_wrong_answer_lapses_back_into_learning():
    state = srs.WordState()
    for _ in range(4):
        srs.grade(state, 5, now=0)
    assert state.status in {srs.STATUS_REVIEW, srs.STATUS_MASTERED}
    srs.grade(state, 0, now=100)
    assert state.status == srs.STATUS_LEARNING
    assert state.lapses == 1
    assert state.wrong == 1
    assert state.due == pytest.approx(100 + srs.LEARNING_STEP)


def test_hint_caps_quality():
    state = srs.WordState()
    srs.grade(state, 5, now=0, hinted=True)
    # hinted recall still counts as correct but earns a smaller ease bonus
    assert state.correct == 1
    assert state.ease <= 2.5


def test_mark_mastered_jumps_the_queue():
    state = srs.WordState()
    srs.mark_mastered(state, now=0)
    assert state.status == srs.STATUS_MASTERED
    assert state.interval_days >= srs.MASTERED_INTERVAL_DAYS
    assert state.reps >= 4


def test_plan_smart_prefers_due_reviews():
    words = [word(f"w{i}") for i in range(12)]
    states = {}
    for index, item in enumerate(words):
        state = srs.WordState()
        if index < 3:
            srs.grade(state, 5, now=0)
            state.due = 50  # already due
            state.status = srs.STATUS_REVIEW
        states[item.key] = state
    plan = srs.plan_session(srs.PlanRequest(
        words=words, states=states, mode="smart", size=5, now=1000, seed=7))
    due_keys = {words[0].key, words[1].key, words[2].key}
    assert due_keys.issubset({item.key for item in plan})
    assert len(plan) == 5


def test_plan_respects_daily_new_limit():
    words = [word(f"w{i}") for i in range(40)]
    plan = srs.plan_session(srs.PlanRequest(
        words=words, states={}, mode="smart", size=10, now=0,
        daily_new_limit=2, new_today=0, seed=1))
    assert len(plan) == 10  # falls back to more words when the new budget is spent


def test_plan_new_budget_zero_still_fills_when_nothing_else():
    words = [word(f"w{i}") for i in range(10)]
    plan = srs.plan_session(srs.PlanRequest(
        words=words, states={}, mode="smart", size=6, now=0,
        daily_new_limit=0, new_today=0, seed=2))
    assert len(plan) == 6


def test_plan_review_mode_only_weak_words():
    words = [word(f"w{i}") for i in range(6)]
    states = {}
    weak = srs.WordState(wrong=2, status=srs.STATUS_REVIEW)
    states[words[0].key] = weak
    plan = srs.plan_session(srs.PlanRequest(
        words=words, states=states, mode="review", size=4, now=0, seed=3))
    assert plan[0].key == words[0].key


def test_free_mode_ignores_schedule_and_budget():
    words = [word(f"w{i}") for i in range(20)]
    states = {words[0].key: srs.mark_mastered(srs.WordState(), now=0)}
    # a due review and a mastered word both stay eligible: free means free.
    states[words[1].key] = srs.WordState(status=srs.STATUS_REVIEW, due=0, reps=2)
    plan = srs.plan_session(srs.PlanRequest(
        words=words, states=states, mode="free", size=10, now=0,
        daily_new_limit=0, new_today=99, seed=4))
    assert len(plan) == 10
    assert plan != srs.plan_session(srs.PlanRequest(
        words=words, states=states, mode="smart", size=10, now=0,
        daily_new_limit=0, new_today=99, seed=4))


def test_free_mode_shows_the_word_like_follow():
    from worddrill.session import DrillSession

    session = DrillSession(words=[word("cache")], mode="free")
    assert session.prompt_variant() == "follow"


def test_plan_is_deterministic_for_a_seed():
    words = [word(f"w{i}") for i in range(30)]
    first = srs.plan_session(srs.PlanRequest(words=words, states={}, mode="smart",
                                             size=8, now=0, seed=99))
    second = srs.plan_session(srs.PlanRequest(words=words, states={}, mode="smart",
                                              size=8, now=0, seed=99))
    assert [w.key for w in first] == [w.key for w in second]


def test_plan_avoids_mastered_words_in_follow_modes():
    words = [word(f"w{i}") for i in range(4)]
    states = {words[0].key: srs.mark_mastered(srs.WordState(), now=0)}
    plan = srs.plan_session(srs.PlanRequest(words=words, states=states,
                                            mode="dictation", size=4, now=0, seed=5))
    assert words[0].key not in {item.key for item in plan}


@pytest.mark.parametrize("mode", srs.MODES)
def test_every_mode_plans_without_crashing(mode):
    words = [word(f"w{i}") for i in range(15)]
    states: dict[str, srs.WordState] = {}
    if mode == "quiz":
        # A quiz only draws from words you have already practised.
        for item in words[:6]:
            srs.grade(states.setdefault(item.key, srs.WordState()), 4, now=0)
    plan = srs.plan_session(srs.PlanRequest(words=words, states=states, mode=mode,
                                            size=5, now=0, seed=11))
    assert len(plan) == 5
    assert len({item.key for item in plan}) == 5


def test_status_counts_and_due_count():
    words = [word(f"w{i}") for i in range(4)]
    states = {words[0].key: srs.mark_mastered(srs.WordState(), now=0)}
    states[words[1].key] = srs.grade(srs.WordState(), 0, now=0)
    counts = srs.status_counts(words, states)
    assert counts[srs.STATUS_MASTERED] == 1
    assert counts[srs.STATUS_LEARNING] == 1
    assert counts[srs.STATUS_NEW] == 2
    assert srs.due_count(words, states, now=700) == 1


def test_local_streak_counts_backwards():
    today = "2026-10-29"
    days = {
        "2026-10-29": {"correct": 3},
        "2026-10-28": {"correct": 1},
        "2026-10-27": {"correct": 0, "wrong": 2},
        "2026-10-26": {"correct": 5},
    }
    # a day with only wrong answers still counts as practice
    assert srs.local_streak(days, today) == 4


def test_local_streak_zero_when_today_empty():
    assert srs.local_streak({"2026-10-28": {"correct": 4}}, "2026-10-29") == 0


def test_next_due_label_reads_naturally():
    assert srs.next_due_label({}, now=0) == "—"
    due_state = srs.WordState(status=srs.STATUS_REVIEW, due=10)
    assert srs.next_due_label({"k": due_state}, now=100) == "现在"
    state = srs.WordState(status=srs.STATUS_REVIEW, due=time.time() + 3600)
    label = srs.next_due_label({"k": state}, now=time.time())
    assert "小时" in label or "分" in label


def test_second_smart_round_does_not_repeat_the_first():
    """Everything you just answered sits in 'learning' until its step is due.

    A fresh round right after must still bring new material, even when the daily
    new-word allowance is already spent.
    """
    words = [word(f"w{i:02d}") for i in range(40)]
    states: dict[str, srs.WordState] = {}
    now = 1_000_000.0

    first = srs.plan_session(srs.PlanRequest(
        words=words, states=states, mode="smart", size=10, now=now, seed=1,
        daily_new_limit=8, new_today=0))
    assert len(first) == 10
    for item in first:
        srs.grade(states.setdefault(item.key, srs.WordState()), 4, now=now)

    second = srs.plan_session(srs.PlanRequest(
        words=words, states=states, mode="smart", size=10, now=now + 1,
        daily_new_limit=8, new_today=len(first)))
    overlap = {w.key for w in first} & {w.key for w in second}
    assert not overlap, f"second round repeats {len(overlap)} words"
    assert len(second) == 10


def test_due_reviews_come_first_in_a_mixed_round():
    words = [word(f"w{i:02d}") for i in range(30)]
    states: dict[str, srs.WordState] = {}
    now = 1_000_000.0
    for item in words[:3]:
        states[item.key] = srs.WordState(status=srs.STATUS_REVIEW, reps=2,
                                         due=now - 60, interval=srs.DAY)
    plan = srs.plan_session(srs.PlanRequest(
        words=words, states=states, mode="smart", size=10, now=now, seed=2))
    due_keys = {item.key for item in words[:3]}
    assert due_keys.issubset({item.key for item in plan})


def test_learning_words_return_only_when_due():
    words = [word(f"w{i:02d}") for i in range(20)]
    states: dict[str, srs.WordState] = {"b:w00": srs.WordState()}
    now = 1_000_000.0
    srs.grade(states["b:w00"], 4, now=now)          # due in ten minutes

    early = srs.plan_session(srs.PlanRequest(
        words=words, states=states, mode="smart", size=5, now=now + 1))
    assert "b:w00" not in {item.key for item in early}

    later = srs.plan_session(srs.PlanRequest(
        words=words, states=states, mode="smart", size=5,
        now=now + srs.LEARNING_STEP + 1))
    assert later[0].key == "b:w00"


def test_quiz_mode_only_uses_studied_words():
    words = [word(f"w{i:02d}") for i in range(20)]
    states: dict[str, srs.WordState] = {}
    now = 1_000_000.0
    for item in words[:4]:                       # only these four were practised
        srs.grade(states.setdefault(item.key, srs.WordState()), 4, now=now)

    plan = srs.plan_session(srs.PlanRequest(
        words=words, states=states, mode="quiz", size=5, now=now))
    studied = {item.key for item in words[:4]}
    assert {item.key for item in plan} == studied, "quiz must not introduce new words"


def test_quiz_prefix_leads_a_smart_round():
    words = [word(f"w{i:02d}") for i in range(30)]
    states: dict[str, srs.WordState] = {}
    now = 1_000_000.0
    for item in words[:5]:
        srs.grade(states.setdefault(item.key, srs.WordState()), 4, now=now)

    plan = srs.plan_session(srs.PlanRequest(
        words=words, states=states, mode="smart", size=8, now=now,
        quiz_count=3, seed=4))
    assert [item.key for item in plan[:3]] == [item.key for item in words[:3]]
    assert len(plan) == 8
    assert len({item.key for item in plan}) == 8


def test_quiz_defaults_to_every_two_rounds():
    from worddrill import store
    assert store.DEFAULT_SETTINGS["quiz_every_sessions"] == 2
    assert store.DEFAULT_SETTINGS["quiz_size"] == 3
