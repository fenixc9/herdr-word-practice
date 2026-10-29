import json
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from worddrill import store  # noqa: E402
from worddrill.srs import WordState  # noqa: E402


def test_progress_roundtrip(tmp_path):
    progress = store.Progress.load(tmp_path)
    state = WordState(reps=2, correct=2, status="review", due=99.0, fav=True)
    progress.set_word_state("b:cache", state)
    progress.record_answer("b:cache", correct=True, elapsed=3.5, was_new=True,
                           now=100.0)
    progress.record_session(now=100.0)
    progress.save()

    reloaded = store.Progress.load(tmp_path)
    again = reloaded.word_state("b:cache")
    assert again.reps == 2 and again.fav is True
    assert reloaded.day(now=100.0)["correct"] == 1
    assert reloaded.day(now=100.0)["new"] == 1
    assert reloaded.day(now=100.0)["sessions"] == 1
    assert reloaded.new_today(now=100.0) == 1
    assert reloaded.totals()["answers"] == 1


def test_missing_state_returns_fresh_word_state(tmp_path):
    progress = store.Progress.load(tmp_path)
    state = progress.word_state("nope")
    assert state.reps == 0 and state.status == "new"


def test_corrupt_progress_is_quarantined(tmp_path):
    path = tmp_path / "progress.json"
    path.write_text("{not json", encoding="utf-8")
    progress = store.Progress.load(tmp_path)
    assert progress.data["words"] == {}
    backups = list(tmp_path.glob("progress.corrupt-*.json"))
    assert backups, "corrupt file should be kept for inspection"


def test_atomic_write_leaves_no_temp_files(tmp_path):
    target = tmp_path / "x.json"
    store.atomic_write_json(target, {"a": 1})
    store.atomic_write_json(target, {"a": 2})
    assert json.loads(target.read_text())["a"] == 2
    assert [p.name for p in tmp_path.iterdir()] == ["x.json"]


def test_file_lock_is_reentrant_across_processes(tmp_path):
    with store.file_lock(tmp_path):
        with store.file_lock(tmp_path):
            pass
    assert (tmp_path / ".lock").exists()


def test_settings_merge_defaults_and_persist(tmp_path):
    settings = store.Settings.load(tmp_path)
    assert settings.get("book") == "cet4"
    assert settings.get("nudge")["min_gap_minutes"] == 45
    settings.data["book"] = "coding"
    settings.data["nudge"]["enabled"] = False
    settings.save()

    reloaded = store.Settings.load(tmp_path)
    assert reloaded.get("book") == "coding"
    assert reloaded.get("nudge")["enabled"] is False
    assert reloaded.get("nudge")["quiet_hours"] == [23, 8], "defaults survive a partial file"


def test_settings_survive_broken_json(tmp_path):
    (tmp_path / "settings.json").write_text("]]]", encoding="utf-8")
    settings = store.Settings.load(tmp_path)
    assert settings.get("book") == "cet4"


def test_prune_words_drops_keys_outside_the_book(tmp_path):
    progress = store.Progress.load(tmp_path)
    progress.set_word_state("cet4:cache", WordState(reps=1))
    progress.set_word_state("gone:word", WordState(reps=1))
    removed = store.prune_words(progress, {"cet4:cache"})
    assert removed == 1
    assert set(progress.data["words"]) == {"cet4:cache"}


def test_reset_clears_everything(tmp_path):
    progress = store.Progress.load(tmp_path)
    progress.set_word_state("b:x", WordState(reps=3))
    progress.record_answer("b:x", True, 1.0, True, now=time.time())
    progress.reset()
    assert progress.data["words"] == {}
    assert progress.data["days"] == {}


def test_last_days_returns_ordered_window(tmp_path):
    progress = store.Progress.load(tmp_path)
    now = time.time()
    progress.record_answer("b:x", True, 1.0, False, now=now)
    days = progress.last_days(7, now=now)
    assert len(days) == 7
    assert days[-1][0] == progress.day_key(now)
    assert days[-1][1]["correct"] == 1
    assert days[0][0] < days[-1][0]


def test_day_key_uses_local_time(tmp_path):
    progress = store.Progress.load(tmp_path)
    stamp = time.mktime((2026, 10, 29, 13, 30, 0, 0, 0, -1))
    assert progress.day_key(stamp) == "2026-10-29"