"""Command line entrypoint for the word-practice plugin.

Everything the plugin does is reachable from here:

    drill      interactive break-time drill (the main event)
    stats      what you have learned so far
    books      list / inspect wordbooks
    import     add your own wordbook
    settings   read and write settings
    event      internal: react to a herdr event (idle nudge)
    startup    internal: prepare state directories

The commands are written to be safe to call from herdr actions and panes:
no interactive prompts unless a TTY is present, JSON output on demand.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Sequence

from . import __version__, herdr, term
from .data import (
    BUNDLED_DIR,
    Wordbook,
    WordbookError,
    available_books,
    find_book,
    import_book,
)
from .session import DrillSession, SessionResult
from .srs import (
    MODES,
    PlanRequest,
    WordState,
    due_count,
    grade,
    local_streak,
    mark_mastered,
    next_due_label,
    plan_session,
    status_counts,
)
from .store import (
    Progress,
    Settings,
    default_config_dir,
    default_state_dir,
    prune_words,
)
from .ui import DrillApp, Theme

NUDGE_FILE = "nudge.json"


# --------------------------------------------------------------------------
# shared helpers
# --------------------------------------------------------------------------
def _state_dir() -> Path:
    return default_state_dir()


def _config_dir() -> Path:
    return default_config_dir()


def _load(settings_override: dict | None = None) -> tuple[Settings, Progress, Path]:
    state_dir = _state_dir()
    settings = Settings.load(_config_dir())
    if settings_override:
        settings.data.update(settings_override)
    progress = Progress.load(state_dir)
    return settings, progress, state_dir


def _resolve_book(settings: Settings, state_dir: Path, override: str | None) -> Wordbook:
    """Pick the active wordbook.

    An explicit ``--book`` is authoritative: a typo should fail loudly. A book
    remembered in settings may legitimately disappear (custom book deleted), so
    that case falls back to the first available book.
    """
    book_id = override or settings.get("book") or "cet4"
    try:
        return find_book(book_id, state_dir)
    except WordbookError:
        if override:
            raise
        books = available_books(state_dir)
        if not books:
            raise
        return books[0]


def _resolve_palette(settings: Settings, override: str | None) -> str:
    """auto | dark | light — ``auto`` asks the terminal for its background."""
    choice = (override or os.environ.get("WORDS_THEME")
              or settings.get("theme") or "auto").lower()
    return choice if choice in {"auto", "dark", "light"} else "auto"


def _resolve_mode(settings: Settings, override: str | None) -> str:
    mode = (override or os.environ.get("HERDR_WORDS_MODE")
            or settings.get("mode") or "smart").lower()
    return mode if mode in MODES else "smart"


def _streak_and_today(progress: Progress, now: float | None = None) -> tuple[int, int]:
    status = progress.data
    today = progress.day_key(now)
    streak = local_streak(status.get("days", {}), today)
    day = status.get("days", {}).get(today, {})
    count = int(day.get("correct", 0)) + int(day.get("wrong", 0))
    return streak, count


def _quiz_due(settings: Settings, progress: Progress) -> int:
    """How many quiz cards this round should start with.

    ``quiz_every_sessions`` (default 3) means: after every three finished rounds,
    the next smart round opens with a short quiz. 0 disables it.
    """
    every = int(settings.get("quiz_every_sessions", 3) or 0)
    if every <= 0:
        return 0
    sessions = int(progress.totals().get("sessions", 0))
    if sessions <= 0 or sessions % every:
        return 0
    return int(settings.get("quiz_size", 3) or 3)


def _plan(settings: Settings, progress: Progress, book: Wordbook, mode: str,
          size: int | None, now: float | None = None,
          quiz_count: int = 0) -> list:
    now = time.time() if now is None else now
    request = PlanRequest(
        words=book.words,
        states=progress.state_map(),
        mode=mode,
        size=size or int(settings.get("session_size", 10) or 10),
        now=now,
        daily_new_limit=int(settings.get("daily_new_limit", 8) or 0),
        new_today=progress.new_today(now, book.id),
        quiz_count=quiz_count,
    )
    return plan_session(request)


def build_session(settings: Settings, progress: Progress, book: Wordbook,
                  mode: str, size: int | None = None,
                  now: float | None = None,
                  quiz_count: int = 0) -> DrillSession:
    words = _plan(settings, progress, book, mode, size, now,
                  quiz_count=0 if mode == "quiz" else quiz_count)
    states = progress.state_map()

    def on_answer(word, state: WordState, answer, correct: bool) -> None:
        was_new = state.reps == 0 and state.correct == 0 and state.wrong == 0
        stamp = time.time()
        grade(state, answer.quality, now=stamp, hinted=answer.hints > 0)
        progress.set_word_state(word.key, state)
        progress.record_answer(word.key, correct, answer.seconds, was_new=was_new,
                               now=stamp)
        progress.save()

    session = DrillSession(
        words=words, mode=mode, book_label=book.name, on_answer=on_answer,
        states=states,
    )
    session.quiz_prefix = quiz_count if mode != "quiz" else 0
    return session


# --------------------------------------------------------------------------
# text rendering (non-interactive)
# --------------------------------------------------------------------------
def plain(text: str) -> str:
    return term.strip_ansi(text)


def frame(session: DrillSession, width: int = 78, height: int = 24, *,
          streak: int = 0, today: int = 0, goal: int = 0,
          help_open: bool = False, color: bool = True,
          message: str = "") -> str:
    lines = __import__("worddrill.ui", fromlist=["render_drill"]).render_drill(
        session, Theme(), width, height, streak=streak, today_count=today,
        daily_goal=goal, help_open=help_open, message=message,
    )
    if not color:
        lines = [plain(line) for line in lines]
    return "\n".join(lines)


def _hr(width: int = 64, char: str = "─") -> str:
    return char * width


def _print_block(title: str, rows: list[str], width: int = 64) -> None:
    print()
    print(term.style(f" {title} ", fg_color=term.HEX["teal"], bold=True))
    print(term.style(_hr(width), term.HEX["surface2"]))
    for row in rows:
        print(row)


def _book_rows(book: Wordbook, progress: Progress, active: bool) -> list[str]:
    states = progress.state_map()
    counts = status_counts(book.words, states)
    mark = term.style("◆", term.HEX["teal"]) if active else " "
    label = f"{mark} {term.pad(book.id, 8)}{book.name}"
    detail = (f"共 {len(book.words):>4}  新 {counts['new']:>4}  "
              f"学习中 {counts['learning']:>3}  复习 {counts['review']:>3}  "
              f"已掌握 {counts['mastered']:>3}")
    return [term.pad(label, 30) + term.style(detail, term.HEX["surface2"])]


def _meter(value: int, goal: int, width: int = 22) -> str:
    fraction = 0.0 if goal <= 0 else min(1.0, value / goal)
    filled = term.style(term.bar(fraction, width), term.HEX["teal"])
    return f"{filled} {value}/{goal}"


# --------------------------------------------------------------------------
# drill
# --------------------------------------------------------------------------
def cmd_drill(args: argparse.Namespace, settings: Settings, progress: Progress,
              state_dir: Path) -> int:
    book = _resolve_book(settings, state_dir, args.book or os.environ.get("HERDR_WORDS_BOOK"))
    mode = _resolve_mode(settings, args.mode)
    size = args.size or int(settings.get("session_size", 10) or 10)
    now = time.time()
    # Drop states for words that no longer exist in this book (renamed book,
    # edited custom wordlist) before planning, not on the exit path.
    if prune_words(progress, book.id, {w.key for w in book.words}):
        progress.save()
    quiz_count = _quiz_due(settings, progress) if mode == "smart" else 0
    session = build_session(settings, progress, book, mode, size, now=now,
                            quiz_count=quiz_count)

    streak, today = _streak_and_today(progress, now)
    goal = int(settings.get("daily_goal", 20) or 0)
    palette_mode = _resolve_palette(settings, args.theme)

    if not session.words:
        if args.json:
            print(json.dumps({"words": [], "mode": mode, "book": book.id}))
            return 0
        print(frame(session, color=not args.no_color, streak=streak,
                    today=today, goal=goal))
        return 0

    if args.plan:
        payload = [{"word": w.word, "cn": w.cn, "pos": w.pos, "key": w.key}
                   for w in session.words]
        if args.json:
            print(json.dumps({"mode": mode, "book": book.id, "words": payload},
                             ensure_ascii=False))
        else:
            for index, item in enumerate(payload, 1):
                print(f"{index:>2}. {term.pad(item['word'], 18)}"
                      f"{term.pad(item['pos'], 8)}{item['cn']}")
        return 0

    if args.once or not sys.stdin.isatty():
        print(frame(session, width=args.width, height=args.height,
                    color=not args.no_color, streak=streak, today=today,
                    goal=goal))
        return 0

    def on_master(word) -> None:
        state = progress.word_state(word.key)
        mark_mastered(state)
        progress.set_word_state(word.key, state)
        progress.save()

    book_entries = [
        {
            "id": item.id,
            "name": item.name,
            "size": len(item.words),
            "detail": item.description,
        }
        for item in available_books(state_dir)
    ]
    holder: dict[str, DrillApp] = {}

    def on_result(result: SessionResult, event: str) -> None:
        progress.record_session()
        progress.save()
        if settings.get("notify_on_finish", True) and result.total:
            herdr.notify(
                f"背完 {result.total} 个单词",
                f"正确 {result.correct}/{result.total} / "
                f"用时 {int(result.elapsed)} 秒",
                sound="done",
            )
        app = holder.get("app")
        if app is None:
            return
        if event == "again":
            # Pick a fresh set of words and keep the UI running.
            due = _quiz_due(settings, progress) if mode == "smart" else 0
            fresh = build_session(settings, progress, book, mode, size,
                                  quiz_count=due)
            new_streak, new_today = _streak_and_today(progress)
            app.quiz_prefix = getattr(fresh, "quiz_prefix", 0)
            app.restart(fresh, streak=new_streak, today_count=new_today)
        elif event == "stats":
            # Keep the summary on screen but surface the numbers in a pane.
            herdr.open_pane("stats", placement="popup", focus=False)

    def on_switch_book(new_book_id: str) -> None:
        """Switch wordbook from inside the TUI and start that book's round."""
        settings.data["book"] = new_book_id
        settings.save()
        active = _resolve_book(settings, state_dir, new_book_id)
        fresh = build_session(settings, progress, active, mode, size)
        new_streak, new_today = _streak_and_today(progress)
        app = holder["app"]
        app.quiz_prefix = getattr(fresh, "quiz_prefix", 0)
        app.set_books(book_entries, active.id, active.name)
        app.set_stats(lambda: stats_snapshot(active.id))
        app.restart(fresh, streak=new_streak, today_count=new_today)

    def stats_snapshot(book_id: str = book.id) -> tuple[int, int]:
        """(这本书今天练过的词数, 这本书累计练过的词数), live from progress.

        Each wordbook keeps its own review pool and its own numbers; the streak
        above stays global because it is a daily habit, not a per-book one.
        """
        return (progress.words_today(book_id=book_id),
                progress.words_in_book(book_id))

    def on_quiz() -> None:
        """Start a short quiz right now, without leaving the drill."""
        fresh = build_session(settings, progress, book, "quiz",
                              int(settings.get("quiz_size", 3) or 3))
        app = holder["app"]
        app.quiz_prefix = 0
        app.restart(fresh, streak=_streak_and_today(progress)[0],
                    today_count=_streak_and_today(progress)[1])

    app = DrillApp(
        session, streak=streak, today_count=today, daily_goal=goal,
        on_master=on_master, on_result=on_result,
        autoplay=args.autoplay, palette=palette_mode,
        books=book_entries, book_id=book.id, on_switch_book=on_switch_book,
        book_name=book.name, quiz_prefix=getattr(session, "quiz_prefix", 0),
        on_quiz=on_quiz, stats=stats_snapshot,
    )
    holder["app"] = app
    try:
        app.run()
    except KeyboardInterrupt:
        pass
    finally:
        # Answers are persisted as they happen; just make sure the file is
        # flushed once on the way out.
        progress.save()
    return 0


# --------------------------------------------------------------------------
# stats
# --------------------------------------------------------------------------
def cmd_stats(args: argparse.Namespace, settings: Settings, progress: Progress,
              state_dir: Path) -> int:
    now = time.time()
    term.set_palette(_resolve_palette(settings, getattr(args, "theme", None)))
    books = available_books(state_dir)
    active = settings.get("book") or (books[0].id if books else "")
    streak, today = _streak_and_today(progress, now)
    goal = int(settings.get("daily_goal", 20) or 0)
    states = progress.state_map()
    totals = progress.totals()

    all_words = [w for book in books for w in book.words]
    overall = status_counts(all_words, states)
    # Each wordbook owns its review pool, so "due" is reported per book too.
    due_by_book = {book.id: due_count(book.words, states, now) for book in books}
    active_due = due_by_book.get(active, 0)

    if args.json:
        payload = {
            "version": __version__,
            "today": today,
            "goal": goal,
            "streak": streak,
            "due": active_due,
            "due_by_book": due_by_book,
            "status": overall,
            "totals": totals,
            "next_due": next_due_label(states, now),
            "books": [
                {
                    "id": book.id,
                    "name": book.name,
                    "active": book.id == active,
                    "size": len(book.words),
                    "status": status_counts(book.words, states),
                }
                for book in books
            ],
            "days": [
                {"date": key, "correct": int(entry.get("correct", 0)),
                 "wrong": int(entry.get("wrong", 0)),
                 "new": int(entry.get("new", 0))}
                for key, entry in progress.last_days(7, now)
            ],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=1))
        return 0

    print()
    print(term.style(" word practice ", fg_color=term.HEX["teal"], bold=True)
          + term.style(f" v{__version__}", term.HEX["surface2"]))
    print(term.style(_hr(), term.HEX["surface2"]))
    print(f" 今日      {_meter(today, goal)}")
    print(f" 待复习    {term.style(str(active_due), term.HEX['peach'])} 个"
          f"  {term.style('(当前词书)', term.HEX['surface2'])}"
          f"   {term.style('下一次: ' + next_due_label(states, now), term.HEX['surface2'])}")
    print(f" 连续      {streak} 天    正确率 "
          f"{totals['accuracy'] * 100:.0f}%    累计 {totals['answers']} 次")

    print()
    print(term.style(" 记忆状态 ", term.HEX["teal"], bold=True))
    total = max(1, sum(overall.values()))
    segments = [
        ("已掌握", overall["mastered"], term.HEX["green"]),
        ("复习中", overall["review"], term.HEX["teal"]),
        ("学习中", overall["learning"], term.HEX["peach"]),
        ("未学", overall["new"], term.HEX["surface2"]),
    ]
    bar_width = 44
    for label, value, colour in segments:
        cells = int(round(bar_width * value / total))
        print(f"  {term.pad(label, 7)}{term.style('█' * cells, colour)}"
              f"{'░' * (bar_width - cells)} {value:>4}")

    _print_block("最近 7 天", _week_rows(progress, now))
    print()
    for book in books:
        for row in _book_rows(book, progress, book.id == active):
            print(row)
    print()
    print(term.style(" 开始训练: words drill   |   帮助: words drill --help",
                     term.HEX["surface2"]))
    print()
    if getattr(args, "wait", False) and sys.stdin.isatty():
        try:
            input(term.style(" 按回车关闭这个窗格", term.HEX["surface2"]))
        except EOFError:
            pass
    return 0


def _week_rows(progress: Progress, now: float) -> list[str]:
    rows: list[str] = []
    days = progress.last_days(7, now)
    peak = max([1] + [int(d.get("correct", 0)) + int(d.get("wrong", 0))
                      for _, d in days])
    for key, entry in days:
        correct = int(entry.get("correct", 0))
        wrong = int(entry.get("wrong", 0))
        total = correct + wrong
        width = int(round(18 * total / peak))
        ok_cells = int(round(width * correct / total)) if total else 0
        bar = (term.style("▇" * ok_cells, term.HEX["green"])
               + term.style("▇" * (width - ok_cells), term.HEX["red"]))
        label = key[5:]
        rows.append(f"  {label}  {bar:<40} {total:>3}")
    return rows


# --------------------------------------------------------------------------
# books / import / settings
# --------------------------------------------------------------------------
def cmd_books(args: argparse.Namespace, settings: Settings, progress: Progress,
              state_dir: Path) -> int:
    books = available_books(state_dir)
    active = settings.get("book")
    states = progress.state_map()
    if args.json:
        print(json.dumps([
            {
                "id": book.id, "name": book.name, "name_en": book.name_en,
                "description": book.description, "custom": book.custom,
                "path": str(book.path), "size": len(book.words),
                "active": book.id == active,
                "status": status_counts(book.words, states),
                "sample": [w.word for w in book.words[:5]],
            }
            for book in books
        ], ensure_ascii=False, indent=1))
        return 0

    if not books:
        print("没有可用的词书。", file=sys.stderr)
        return 1

    if args.words:
        book = _resolve_book(settings, state_dir, args.words)
        for word in book.words:
            line = (term.pad(word.word, 18) + term.pad(word.ipa, 20)
                    + term.pad(word.pos, 8) + word.cn)
            print(term.strip_ansi(line))
        return 0

    print()
    for book in books:
        rows = _book_rows(book, progress, book.id == active)
        for row in rows:
            print(row)
        if book.description:
            print(" " * 10 + term.style(book.description, term.HEX["surface2"]))
    print()
    print(term.style(f" 词书目录: {BUNDLED_DIR}", term.HEX["surface2"]))
    print(term.style(f" 自定义词书: {state_dir / 'books'}", term.HEX["surface2"]))
    print()
    return 0


def cmd_import(args: argparse.Namespace, settings: Settings, progress: Progress,
               state_dir: Path) -> int:
    try:
        book = import_book(Path(args.path), state_dir, book_id=args.id,
                           name=args.name)
    except WordbookError as error:
        print(f"导入失败: {error}", file=sys.stderr)
        return 1
    if args.use:
        settings.data["book"] = book.id
        settings.save()
    print(f"已导入 {book.name} ({book.id})，共 {len(book.words)} 个单词。")
    return 0


def _coerce(raw: str):
    lowered = raw.strip().lower()
    if lowered in {"true", "yes", "on"}:
        return True
    if lowered in {"false", "no", "off"}:
        return False
    if lowered in {"none", "null"}:
        return None
    for caster in (int, float):
        try:
            return caster(raw)
        except ValueError:
            continue
    if raw.strip()[:1] in "[{":
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass
    return raw


def _set_dotted(data: dict, dotted: str, value) -> None:
    parts = dotted.split(".")
    cursor = data
    for part in parts[:-1]:
        node = cursor.get(part)
        if not isinstance(node, dict):
            node = {}
            cursor[part] = node
        cursor = node
    cursor[parts[-1]] = value


def cmd_settings(args: argparse.Namespace, settings: Settings, progress: Progress,
                 state_dir: Path) -> int:
    changed = False
    for assignment in args.assignments:
        if "=" not in assignment:
            print(f"忽略无效设置 '{assignment}'（需要 key=value）", file=sys.stderr)
            continue
        key, raw = assignment.split("=", 1)
        _set_dotted(settings.data, key.strip(), _coerce(raw))
        changed = True
    if changed:
        settings.save()

    if args.json:
        print(json.dumps(settings.data, ensure_ascii=False, indent=1))
        return 0

    print()
    print(term.style(f" 设置文件 {settings.path}", term.HEX["surface2"]))
    print(term.style(_hr(), term.HEX["surface2"]))
    for key, value in settings.data.items():
        if isinstance(value, dict):
            for sub_key, sub_value in value.items():
                print(f"  {key}.{sub_key:<22}{sub_value}")
        else:
            print(f"  {key:<26}{value}")
    print()
    print()
    return 0


def cmd_reset(args: argparse.Namespace, settings: Settings, progress: Progress,
              state_dir: Path) -> int:
    if not args.yes:
        print("这会清空所有学习进度。确认请加 --yes。", file=sys.stderr)
        return 2
    progress.reset()
    progress.save()
    print("进度已清空。")
    return 0


# --------------------------------------------------------------------------
# herdr integration
# --------------------------------------------------------------------------
def cmd_event(args: argparse.Namespace, settings: Settings, progress: Progress,
              state_dir: Path) -> int:
    payload = herdr.event_payload()
    if not payload and args.payload:
        try:
            payload = json.loads(args.payload)
        except json.JSONDecodeError:
            herdr.stderr("event payload is not JSON")
            return 1
    if not payload:
        if not args.force:
            herdr.stderr("no event payload (set HERDR_PLUGIN_EVENT_JSON or --payload)")
            return 1
        # `--force` is also used by the "nudge me now" action, which herdr
        # dispatches without an event payload.
        payload = {}

    event = os.environ.get("HERDR_PLUGIN_EVENT") or args.event or "unknown"
    status = herdr.find_status(payload)
    nudge = settings.get("nudge", {}) or {}
    enabled = bool(nudge.get("enabled", True))
    min_gap = int(nudge.get("min_gap_minutes", 45) or 0)
    quiet = nudge.get("quiet_hours", [23, 8]) or [23, 8]
    quiet_hours = (int(quiet[0]), int(quiet[1]))

    record_path = state_dir / NUDGE_FILE
    record = herdr.load_json(record_path, {})
    if not isinstance(record, dict):
        record = {}
    last_nudge = float(record.get("last", 0) or 0)
    now = time.time()

    ok, reason = herdr.should_nudge(status, last_nudge, now, min_gap, quiet_hours)
    if args.force:
        ok, reason = True, "forced"

    streak, today = _streak_and_today(progress, now)
    goal = int(settings.get("daily_goal", 20) or 0)
    books = available_books(state_dir)
    states = progress.state_map()
    # The reminder looks at the book you are currently studying.
    active_book = settings.get("book") or (books[0].id if books else "")
    current = next((b for b in books if b.id == active_book), None)
    due = due_count(current.words, states, now) if current else 0
    remaining = max(0, goal - today)

    if args.json:
        print(json.dumps({
            "event": event, "status": status, "nudge": ok, "reason": reason,
            "book": active_book, "due": due, "today": today, "goal": goal,
            "streak": streak,
        }, ensure_ascii=False))
        if not ok:
            return 0

    if not ok:
        herdr.stderr(f"skip nudge: {reason}")
        return 0
    if not enabled:
        herdr.stderr("skip nudge: disabled in settings")
        return 0
    if remaining == 0 and due == 0 and not args.force:
        herdr.stderr("skip nudge: goal already reached and nothing due")
        return 0

    body_bits = []
    if due:
        body_bits.append(f"{due} 个到期")
    if remaining:
        body_bits.append(f"今日还差 {remaining} 个")
    if streak:
        body_bits.append(f"连续 {streak} 天")
    body = " / ".join(body_bits) or "随时来一组"
    herdr.notify("该背单词了", body, sound="request")

    if settings.get("nudge", {}).get("auto_open", False):
        herdr.open_pane("break", placement="popup", focus=False)

    record.update({"last": now, "status": status, "event": event})
    herdr.save_json(record_path, record)
    return 0


def cmd_open_pane(args: argparse.Namespace, settings: Settings, progress: Progress,
                  state_dir: Path) -> int:
    """Open a drill/stats pane. herdr actions get no PTY, so they call this."""
    entrypoint = args.entrypoint or "break"
    env: dict[str, str] = {}
    if args.mode:
        env["HERDR_WORDS_MODE"] = args.mode
    if args.book:
        env["HERDR_WORDS_BOOK"] = args.book
    result, error = herdr.open_pane_detailed(
        entrypoint, placement=args.placement, env=env or None,
        focus=not args.no_focus)
    if error == "ui_busy":
        # A popup is already open — the drill is right in front of the user, so
        # pressing the key again is a no-op instead of an error.
        if args.json:
            print(json.dumps({"status": "already open"}, ensure_ascii=False))
        return 0
    if error is not None or result is None:
        herdr.stderr(f"无法打开窗格: {error or 'unknown error'}")
        return 1
    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    return 0


def cmd_startup(args: argparse.Namespace, settings: Settings, progress: Progress,
                state_dir: Path) -> int:
    for directory in (state_dir, state_dir / "books", _config_dir()):
        directory.mkdir(parents=True, exist_ok=True)
    streak, today = _streak_and_today(progress)
    books = available_books(state_dir)
    due = due_count([w for book in books for w in book.words],
                    progress.state_map())
    line = (f"word-practice v{__version__}: {len(books)} books, "
            f"{due} due, {today} today, streak {streak}")
    print(line)
    return 0


SETUP_MARKER = "# word-practice: 在 vibe coding 的间隙背单词"
KEYBLOCK = f"""{SETUP_MARKER}（prefix+w 打开一组，约 90 秒）。
[[keys.command]]
key = "prefix+w"
type = "plugin_action"
command = "herdr-word-practice.drill"
description = "背单词"

[[keys.command]]
key = "prefix+shift+w"
type = "plugin_action"
command = "herdr-word-practice.dictation"
description = "背单词：默写"

[[keys.command]]
key = "prefix+alt+w"
type = "plugin_action"
command = "herdr-word-practice.stats"
description = "背单词：学习进度"
"""


def _plugin_root() -> Path:
    """The checkout herdr is running us from (works for link and GitHub install)."""
    return Path(__file__).resolve().parent.parent


def _herdr_config() -> Path:
    explicit = os.environ.get("HERDR_CONFIG")
    if explicit:
        return Path(explicit).expanduser()
    home = os.environ.get("XDG_CONFIG_HOME")
    base = Path(home) if home else Path.home() / ".config"
    return base / "herdr" / "config.toml"


def _words_on_path(bin_dir: Path) -> bool:
    """Is ``words`` reachable from a login shell?

    Actions run with herdr's own environment, which may not include
    ``~/.local/bin`` even when the user's shell does — so ask the shell.
    """
    shell = os.environ.get("SHELL") or "/bin/sh"
    if ":" + str(bin_dir) + ":" in ":" + os.environ.get("PATH", "") + ":":
        return True
    try:
        proc = subprocess.run([shell, "-lc", "command -v words"],
                              capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0


def cmd_setup(args: argparse.Namespace, settings: Settings, progress: Progress,
              state_dir: Path) -> int:
    """Wire the plugin into herdr: keybindings, the `words` command, reload.

    Everything here is idempotent, so `herdr plugin action invoke
    herdr-word-practice.setup` is safe to run again after an update.
    """
    root = _plugin_root()
    config = _herdr_config()
    bin_dir = Path(os.environ.get("WORDS_BIN_DIR", "~/.local/bin")).expanduser()
    steps: list[str] = []
    dry = bool(getattr(args, "dry_run", False))

    # 1. keybindings
    try:
        text = config.read_text(encoding="utf-8")
    except OSError:
        text = ""
    if SETUP_MARKER in text:
        steps.append(f"键位: 已配置，跳过 ({config})")
    else:
        if not dry:
            config.parent.mkdir(parents=True, exist_ok=True)
            with config.open("a", encoding="utf-8") as handle:
                handle.write(("\n" if text and not text.endswith("\n") else "") + KEYBLOCK)
        steps.append(f"键位: 追加 prefix+w / prefix+shift+w / prefix+alt+w -> {config}")

    # 2. the `words` command
    target = root / "scripts" / "words"
    link = bin_dir / "words"
    on_path = _words_on_path(bin_dir)
    if link.is_symlink() and Path(os.path.realpath(link)) == Path(os.path.realpath(target)):
        steps.append(f"words 命令: 已指向 {target}")
    else:
        if not dry:
            bin_dir.mkdir(parents=True, exist_ok=True)
            if link.is_symlink() or link.exists():
                link.unlink()
            link.symlink_to(target)
        steps.append(f"words 命令: 链接 {link} -> {target}")
    if not on_path:
        # Never edit the user's shell startup files — just say what to add.
        steps.append(f"注意: {bin_dir} 不在 PATH 里，加一行即可: "
                     f'export PATH="{bin_dir}:$PATH"')

    # 3. reload so the keybindings take effect
    if not dry:
        reloaded = herdr.run_herdr_raw(["server", "reload-config"])
        ok = bool(reloaded) and not isinstance(reloaded.get("error"), dict)
        steps.append("重载配置: " + ("ok" if ok else "失败，手动跑 herdr server reload-config"))

    if args.json:
        print(json.dumps({"root": str(root), "config": str(config),
                          "steps": steps, "dry_run": dry}, ensure_ascii=False,
                         indent=1))
        return 0
    print()
    for step in steps:
        print(f"  {step}")
    print()
    print("装好了: 在 herdr 里按 prefix+w 开始（第一次会开一个卡片窗格）。")
    print("其他命令: words books / words stats / words settings / words doctor")
    return 0


def cmd_doctor(args: argparse.Namespace, settings: Settings, progress: Progress,
               state_dir: Path) -> int:
    checks: list[tuple[str, bool, str]] = []
    checks.append(("python", sys.version_info >= (3, 9), sys.version.split()[0]))
    checks.append(("state dir", state_dir.is_dir(), str(state_dir)))
    checks.append(("config dir", _config_dir().is_dir(), str(_config_dir())))
    checks.append(("herdr cli", herdr.herdr_bin() is not None,
                   herdr.herdr_bin() or "herdr not on PATH"))
    books = available_books(state_dir)
    checks.append(("wordbooks", bool(books),
                   ", ".join(f"{b.id}({len(b)})" for b in books) or "none"))

    if args.json:
        print(json.dumps([{"check": name, "ok": ok, "detail": detail}
                          for name, ok, detail in checks], ensure_ascii=False,
                         indent=1))
    else:
        for name, ok, detail in checks:
            mark = (term.style("ok  ", term.HEX["green"]) if ok
                    else term.style("fail", term.HEX["red"]))
            print(f"  {mark} {term.pad(name, 16)}{detail}")
    return 0 if all(ok for _, ok, _ in checks) else 1


# --------------------------------------------------------------------------
# argument parsing
# --------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="words",
        description="在 vibe coding 的间隙背单词（间隔重复 + 打字回忆）。",
    )
    parser.add_argument("--version", action="version", version=f"words {__version__}")
    sub = parser.add_subparsers(dest="command")

    drill = sub.add_parser("drill", help="开始一组训练")
    drill.add_argument("-m", "--mode", choices=MODES, help="训练模式")
    drill.add_argument("-b", "--book", help="词书 id")
    drill.add_argument("-n", "--size", type=int, help="这一组的词数")
    drill.add_argument("--theme", choices=("auto", "dark", "light"),
                       help="界面配色（默认 auto：读终端背景色）")
    drill.add_argument("--no-color", action="store_true", help="关闭颜色")
    drill.add_argument("--plan", action="store_true", help="只列出本轮单词，不进界面")
    drill.add_argument("--once", action="store_true", help="渲染一帧后退出（用于预览）")
    drill.add_argument("--json", action="store_true", help="JSON 输出")
    drill.add_argument("--width", type=int, default=78)
    drill.add_argument("--height", type=int, default=24)
    drill.add_argument("--autoplay", nargs="?", const=True, default=False,
                       help=argparse.SUPPRESS)
    drill.set_defaults(func=cmd_drill)

    stats = sub.add_parser("stats", help="查看学习进度")
    stats.add_argument("--json", action="store_true")
    stats.add_argument("--wait", action="store_true",
                       help="打印后等待回车（用于窗格）")
    stats.add_argument("--theme", choices=("auto", "dark", "light"))
    stats.set_defaults(func=cmd_stats)

    books = sub.add_parser("books", help="列出词书")
    books.add_argument("--json", action="store_true")
    books.add_argument("--words", metavar="BOOK", help="打印某本词书的全部单词")
    books.set_defaults(func=cmd_books)

    importer = sub.add_parser("import", help="导入自定义词书（json/csv/tsv）")
    importer.add_argument("path")
    importer.add_argument("--id")
    importer.add_argument("--name")
    importer.add_argument("--use", action="store_true", help="导入后切换为当前词书")
    importer.set_defaults(func=cmd_import)

    settings = sub.add_parser("settings", help="查看或修改设置")
    settings.add_argument("assignments", nargs="*", metavar="key=value")
    settings.add_argument("--json", action="store_true")
    settings.set_defaults(func=cmd_settings)

    reset = sub.add_parser("reset", help="清空学习进度")
    reset.add_argument("--yes", action="store_true")
    reset.set_defaults(func=cmd_reset)

    event = sub.add_parser("event", help="herdr 事件钩子（内部使用）")
    event.add_argument("--payload", help="JSON 负载（默认读 HERDR_PLUGIN_EVENT_JSON）")
    event.add_argument("--event", help="事件名（默认读 HERDR_PLUGIN_EVENT）")
    event.add_argument("--force", action="store_true", help="忽略节流和静默时段")
    event.add_argument("--json", action="store_true")
    event.set_defaults(func=cmd_event)

    startup = sub.add_parser("startup", help="启动时准备目录（内部使用）")
    startup.set_defaults(func=cmd_startup)

    open_pane = sub.add_parser("open-pane", help="在 herdr 里打开训练窗格（内部使用）")
    open_pane.add_argument("entrypoint", nargs="?", default="break")
    open_pane.add_argument("-m", "--mode", choices=MODES)
    open_pane.add_argument("-b", "--book")
    open_pane.add_argument("--placement", default="popup")
    open_pane.add_argument("--no-focus", action="store_true")
    open_pane.add_argument("--json", action="store_true")
    open_pane.set_defaults(func=cmd_open_pane)

    setup = sub.add_parser("setup", help="把插件接进 herdr（键位 + words 命令 + 重载）")
    setup.add_argument("--dry-run", action="store_true", help="只打印将要做什么")
    setup.add_argument("--json", action="store_true")

    doctor = sub.add_parser("doctor", help="自检环境")
    doctor.add_argument("--json", action="store_true")
    doctor.set_defaults(func=cmd_doctor)

    setup.set_defaults(func=cmd_setup)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    if not getattr(args, "func", None):
        parser.print_help()
        return 0

    settings, progress, state_dir = _load()
    try:
        return int(args.func(args, settings, progress, state_dir) or 0)
    except WordbookError as error:
        print(f"词书错误: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
