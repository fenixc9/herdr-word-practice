"""The drill TUI: rendering plus raw keyboard handling.

Keyboard-only, one card at a time, designed to fit a Herdr popup and to be
readable in a narrow split.
"""

from __future__ import annotations

import os
import select
import signal
import sys
import time
from dataclasses import dataclass

from . import term
from .data import Word
from .session import Answer, DrillSession, SessionResult
from .srs import MODE_HINTS, MODE_LABELS, next_due_label

RESULT_HOLD_OK = 0.6
RESULT_HOLD_BAD = 2.0
TICK = 0.1
ESCAPE_GRACE = 0.025   # how long a lone ESC waits to become an Escape key


@dataclass
class Theme:
    colors: bool = True
    palette: str = ""      # "", "dark", "light"

    def __post_init__(self) -> None:
        self.colors = bool(self.colors) and term.color_supported()
        if self.palette:
            term.set_palette(self.palette)

    def paint(self, text: str, fg_color: str | None = None, bg_color: str | None = None,
              bold: bool = False, dim: bool = False, italic: bool = False,
              underline: bool = False, reverse: bool = False) -> str:
        return term.style(
            text, fg_color=fg_color, bg_color=bg_color, bold=bold, dim=dim,
            italic=italic, underline=underline, reverse=reverse, colors=self.colors,
        )


class Painter:
    """Lays out rows and keeps every line exactly ``width`` cells wide."""

    def __init__(self, width: int, height: int, theme: Theme):
        self.width = width
        self.height = height
        self.theme = theme
        self.rows: list[str] = []

    def add(self, row: str = "") -> None:
        if len(self.rows) < self.height:
            self.rows.append(term.pad(row, self.width))

    def blank(self, count: int = 1) -> None:
        for _ in range(count):
            self.add("")

    def render(self) -> list[str]:
        while len(self.rows) < self.height:
            self.rows.append(" " * self.width)
        return self.rows[: self.height]


HELP_LINES = [
    ("Tab", "提示下一个字母"),
    ("Enter", "提交 / 下一张"),
    ("Esc", "退出（自动保存）"),
    ("Ctrl+R", "重播发音"),
    ("Ctrl+F", "收藏 / 取消收藏"),
    ("Ctrl+M", "标记为已掌握"),
    ("Ctrl+S", "静音开关"),
    ("?", "打开这个帮助"),
    ("1-4", "自测模式：不认识 / 模糊 / 认识 / 太简单"),
]


def frame_border(painter: Painter, title: str, subtitle: str = "",
                 right: str = "") -> None:
    theme = painter.theme
    width = painter.width
    title_text = theme.paint(f" {title} ", "mauve", bold=True)
    subtitle_text = theme.paint(f"| {subtitle} ", "overlay1") if subtitle else ""
    right_text = theme.paint(f" {right} ", "subtext") if right else ""
    used = 1 + term.text_width(f" {title} ")
    if subtitle:
        used += term.text_width(f"| {subtitle} ")
    right_used = term.text_width(f" {right} ") if right else 0
    # used already counts the leading "╭"; only "╮" is still to come.
    fill = max(0, width - used - right_used - 1)
    painter.add(
        theme.paint("╭", "surface2") + title_text + subtitle_text
        + theme.paint("─" * fill, "surface1") + right_text
        + theme.paint("╮", "surface2")
    )


def top_rule(painter: Painter) -> None:
    painter.add(painter.theme.paint("├" + "─" * (painter.width - 2) + "┤", "surface2"))


def bottom_rule(painter: Painter) -> None:
    painter.add(painter.theme.paint("├" + "─" * (painter.width - 2) + "┤", "surface2"))


def frame_footer(painter: Painter, keys: list[tuple[str, str]]) -> None:
    theme = painter.theme
    chunks = [
        theme.paint(key, "lavender", bold=True) + theme.paint(f" {label}", "overlay1")
        for key, label in keys
    ]
    text = theme.paint("  |  ", "surface2").join(chunks)
    # "╰─ " (3) + body + " ─╯" (3) must add up to exactly the frame width.
    painter.add(
        theme.paint("╰─ ", "surface2")
        + term.pad(term.truncate(text, max(0, painter.width - 6)), max(0, painter.width - 6))
        + theme.paint(" ─╯", "surface2")
    )


def centered(painter: Painter, text: str, fg_color: str | None = None,
             bold: bool = False, dim: bool = False, italic: bool = False) -> None:
    width = term.text_width(term.strip_ansi(text))
    padding = max(0, (painter.width - width) // 2)
    painter.add(" " * padding + painter.theme.paint(
        text, fg_color=fg_color, bold=bold, dim=dim, italic=italic))


def _format_clock(seconds: float) -> str:
    seconds = max(0, int(seconds))
    minutes, secs = divmod(seconds, 60)
    if minutes >= 60:
        hours, minutes = divmod(minutes, 60)
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def _fit(painter: Painter, limit: int) -> None:
    """Make room for the footer by dropping padding, never content.

    Small popups (or a tall verdict block) can overflow the frame. Blank rows
    are the cheapest thing to lose, so they go first; if the card itself is too
    tall we simply let it clip rather than lose the status line.
    """
    limit = max(0, limit)
    while len(painter.rows) > limit:
        for index in range(len(painter.rows) - 1, -1, -1):
            if not term.strip_ansi(painter.rows[index]).strip():
                del painter.rows[index]
                break
        else:
            return
    while len(painter.rows) < limit:
        painter.blank(1)


def render_drill(session: DrillSession, theme: Theme, width: int, height: int,
                 *, streak: int = 0, today_count: int = 0, daily_goal: int = 0,
                 sound_on: bool = True, help_open: bool = False,
                 message: str = "") -> list[str]:
    painter = Painter(width, height, theme)
    mode_label = MODE_LABELS.get(session.mode, session.mode)

    header_right = f"{min(session.index + 1, session.total)}/{session.total}"
    if streak:
        header_right += f"  🔥{streak}"
    frame_border(painter, "herdr words", mode_label, header_right)
    top_rule(painter)

    if help_open:
        return _render_help(painter, session)
    if not session.words:
        return _render_empty(painter, session)
    if session.phase == "done":
        return _render_summary(painter, session, theme)

    word = session.current
    if word is None:
        return _render_empty(painter, session)

    variant = session.prompt_variant(word)
    inner = max(8, width - 8)
    painter.blank(1)

    if variant == "selfcheck":
        _render_selfcheck_card(painter, session, word, inner)
    else:
        _render_card(painter, session, word, inner, variant)

    painter.blank(1)
    if variant != "selfcheck":
        _render_input(painter, session, word)

    painter.blank(1)
    if session.phase == "result" and session.last_answer:
        _render_verdict(painter, session.last_answer, inner)
    elif message:
        centered(painter, message, "teal")

    _fit(painter, height - 3)
    bottom_rule(painter)
    _render_status(painter, session, today_count, daily_goal, sound_on)
    _render_keys(painter, session, variant)
    return painter.render()


def rpad(text: str, width: int) -> str:
    """Pad on the right to a *display* width (CJK is two cells, not two chars)."""
    return term.pad(text, width)


def lpad(text: str, width: int) -> str:
    """Pad on the left to a *display* width."""
    space = width - term.text_width(text)
    return " " * space + text if space > 0 else term.truncate(text, width)


def _card_meta(word: Word) -> str:
    return "  ".join(part for part in (word.ipa, word.pos) if part)


def _render_card(painter: Painter, session: DrillSession, word: Word,
                 inner: int, variant: str) -> None:
    show_word = variant == "follow" or session.phase == "result"
    if show_word:
        centered(painter, word.word, "text", bold=True)
    else:
        # Masked prompt: show length as underscores, keeping spaces/hyphens.
        centered(painter, word.length_hint, "surface2", bold=True)

    meta = _card_meta(word)
    if meta and variant != "spelling":
        centered(painter, meta, "overlay1")

    meaning = word.cn
    if meaning:
        centered(painter, meaning, "subtext")

    example = word.en
    if variant in {"dictation"}:
        example = word.blanked_example()
    if variant == "spelling":
        example = ""
    if example:
        painter.blank(1)
        for line in term.wrap(example, inner, max_lines=2):
            centered(painter, line, "surface2", italic=True)
        if variant != "follow" and word.zh and session.phase != "result":
            pass
    elif word.en and variant == "follow":
        painter.blank(1)
        for line in term.wrap(word.en, inner, max_lines=2):
            centered(painter, line, "surface2", italic=True)

    if variant == "follow" and word.zh:
        for line in term.wrap(word.zh, inner, max_lines=1):
            centered(painter, line, "surface2")
    if session.phase == "result" and session.last_answer and not session.last_answer.correct:
        # In a result state the Chinese example translation helps the postmortem.
        for line in term.wrap(word.zh, inner, max_lines=1):
            centered(painter, line, "surface2")


def _render_input(painter: Painter, session: DrillSession, word: Word) -> None:
    theme = painter.theme
    box_width = min(max(28, len(word.word) + 16), max(24, painter.width - 8))
    left_pad = max(0, (painter.width - box_width) // 2)
    inner_width = box_width - 4

    typed = session.typed
    matched = 0
    for index, char in enumerate(typed):
        if index < len(word.word) and char.lower() == word.word[index].lower():
            matched += 1
        else:
            break
    wrong_part = typed[matched:]
    rendered = theme.paint(typed[:matched], "green", bold=True)
    if wrong_part:
        rendered += theme.paint(wrong_part, "red", bold=True, underline=True)

    body = ""
    if typed:
        body = rendered
    elif session.phase == "result" and session.last_answer and not session.last_answer.correct:
        body = theme.paint(session.last_answer.typed, "red", underline=True)
    elif session.hints:
        body = theme.paint(word.word[: session.hints], "green")
    else:
        body = theme.paint("开始输入...", "surface2")

    if session.phase == "result" and session.last_answer and session.last_answer.correct:
        box_color = "green"
    elif session.phase == "result":
        box_color = "red"
    else:
        box_color = "surface1"

    content_width = max(4, inner_width - 1)
    caret = theme.paint("▏", "mauve", reverse=True) if session.phase == "typing" else " "
    # The label "╭─ 输入 " is 8 cells (CJK counts double), so the fill has to be
    # box_width - 9 to make the top edge exactly as wide as the sides below it.
    painter.add(" " * left_pad
                + theme.paint("╭─ 输入 " + "─" * (box_width - 9) + "╮", box_color))
    painter.add(
        " " * left_pad
        + theme.paint("│ ", box_color)
        + term.pad(body, content_width)
        + caret
        + theme.paint(" │", box_color)
    )
    painter.add(" " * left_pad + theme.paint("╰" + "─" * (box_width - 2) + "╯", box_color))

    hint_parts = []
    if session.hints and session.phase == "typing":
        hint_parts.append(theme.paint(f"已提示 {session.hints}/{len(word.word)}", "peach"))
    hint_parts.append(theme.paint(f"{len(word.word)} 个字母", "surface2"))
    painter.add(" " * left_pad + theme.paint("  ", "surface2").join(hint_parts))


def _render_selfcheck_card(painter: Painter, session: DrillSession, word: Word,
                           inner: int) -> None:
    theme = painter.theme
    centered(painter, word.word, "text", bold=True)
    meta = _card_meta(word)
    if meta:
        centered(painter, meta, "overlay1")
    centered(painter, word.cn, "subtext")
    if word.en:
        painter.blank(1)
        for line in term.wrap(word.en, inner, max_lines=2):
            centered(painter, line, "surface2", italic=True)
    if word.zh:
        for line in term.wrap(word.zh, inner, max_lines=1):
            centered(painter, line, "surface2")

    painter.blank(1)
    chips = []
    for key, label, color in (("1", "不认识", "red"), ("2", "模糊", "peach"),
                              ("3", "认识", "green"), ("4", "太简单", "teal")):
        chips.append(
            theme.paint(f" {key} ", "crust", bg_color=color)
            + theme.paint(f" {label} ", "subtext")
        )
    centered(painter, "  ".join(chips))
    if session.phase == "result" and session.last_answer:
        painter.blank(1)
        answer = session.last_answer
        if answer.correct:
            centered(painter, f"✓ 记为「{_quality_label(answer.quality)}」", "green", bold=True)
        else:
            centered(painter, "↺ 已加入复习队列", "peach", bold=True)


def _quality_label(quality: int) -> str:
    return {0: "不认识", 1: "不认识", 2: "模糊", 3: "认识", 4: "认识", 5: "太简单"}.get(
        quality, "认识")


def _render_verdict(painter: Painter, answer: Answer, inner: int) -> None:
    word = answer.word
    if answer.correct:
        text = "✓  正确"
        if answer.hints:
            text += f"  |  用了 {answer.hints} 个提示"
        else:
            text += "  |  一次拼对"
        centered(painter, text, "green", bold=True)
    else:
        if answer.skipped:
            centered(painter, "->  已跳过", "peach", bold=True)
        else:
            centered(painter, "✗  拼写错误", "red", bold=True)
        centered(painter, f"正确答案  {word.word}", "yellow", bold=True)
        if answer.typed.strip():
            centered(painter, f"你输入的是  {answer.typed.strip()}", "surface2")

    # After the verdict, connect the word to the things that make it stick:
    # collocations, near synonyms, and the root it grew from.
    if word.phr:
        for line in term.wrap("搭配  " + " / ".join(word.phr[:2]),
                              max(16, inner), max_lines=1):
            centered(painter, line, "overlay1")
    if word.syn:
        centered(painter, "近义  " + " / ".join(word.syn[:3]), "overlay1")
    if word.root:
        for line in term.wrap("词源  " + word.root, max(16, inner), max_lines=1):
            centered(painter, line, "surface2")


def _render_status(painter: Painter, session: DrillSession, today_count: int,
                   daily_goal: int, sound_on: bool) -> None:
    theme = painter.theme
    done = len(session.answers)
    correct = sum(1 for a in session.answers if a.correct)
    accuracy = correct / done if done else 0.0
    bar_width = max(6, min(20, painter.width // 4))
    if session.total:
        progress_bar = theme.paint(term.bar(session.progress, bar_width), "mauve")
        percent = theme.paint(f"{int(session.progress * 100):3d}%", "subtext")
    else:
        progress_bar = theme.paint("▱" * bar_width, "surface2")
        percent = theme.paint("  -", "subtext")
    stats = (theme.paint(f"✓{correct}", "green") + theme.paint("/", "surface2")
             + theme.paint(f"✗{done - correct}", "red"))
    acc = (theme.paint(f"{int(accuracy * 100)}%", "subtext") if done
           else theme.paint("-", "surface2"))
    goal = theme.paint(f"今日 {today_count}/{daily_goal}", "blue") if daily_goal else ""
    elapsed = theme.paint(_format_clock(session.elapsed), "overlay1")
    mute = theme.paint("🔊", "teal") if sound_on else theme.paint("🔇", "surface2")
    parts = [part for part in (progress_bar, percent, stats, acc, goal, elapsed, mute)
             if part]
    # Drop whole segments from the right instead of slicing a CJK glyph in half.
    budget = painter.width - 2
    kept: list[str] = []
    for part in parts:
        trial = "   ".join([*kept, part])
        if term.text_width(term.strip_ansi(trial)) > budget:
            break
        kept.append(part)
    painter.add(" " + term.pad("   ".join(kept), budget))


def _render_keys(painter: Painter, session: DrillSession, variant: str) -> None:
    theme = painter.theme
    if session.phase == "done":
        keys = [("⏎", "再来一组"), ("⇥", "进度"), ("esc/⌃c", "退出")]
    elif session.phase == "result":
        keys = [("⏎", "下一张"), ("⌃r", "发音"), ("⌃f", "收藏"), ("esc/⌃c", "退出")]
    elif variant == "selfcheck":
        keys = [("1-4", "自评"), ("⌃r", "发音"), ("⌃f", "收藏"), ("?", "帮助"),
                ("esc/⌃c", "退出")]
    else:
        keys = [("⏎", "提交"), ("⇥", "提示"), ("⌃r", "发音"), ("⌃f", "收藏"),
                ("⌃m", "掌握"), ("?", "帮助"), ("esc/⌃c", "退出")]
    budget = painter.width - 6          # "╰─ " + " ─╯"
    sep = theme.paint("  |  ", "surface2")

    def render(selection) -> str:
        return sep.join(
            theme.paint(key, "lavender", bold=True) + theme.paint(f" {label}", "overlay1")
            for key, label in selection)

    # Always keep the first and last hint (quit stays reachable); fill the middle
    # only as far as it fits, so nothing is ever cut mid-glyph.
    kept = [keys[0]]
    for item in keys[1:-1]:
        trial = term.text_width(term.strip_ansi(render([*kept, item, keys[-1]])))
        if trial > budget:
            break
        kept.append(item)
    kept.append(keys[-1])
    body = render(kept)
    if term.text_width(term.strip_ansi(body)) > budget:
        body = term.truncate(body, budget)
    painter.add(theme.paint("╰─ ", "surface2") + term.pad(body, budget)
                + theme.paint(" ─╯", "surface2"))


def _render_summary(painter: Painter, session: DrillSession, theme: Theme) -> list[str]:
    result = session.result()
    painter.blank(1)
    centered(painter, "训练完成", "green", bold=True)
    painter.blank(1)
    centered(painter, f"正确率  {int(result.accuracy * 100)}%    {result.correct}/{result.total}",
             "text")
    pace = (f"{result.words_per_minute:.1f} 词/分"
            if result.words_per_minute else "-")
    centered(painter, f"用时  {_format_clock(result.elapsed)}    {pace}", "subtext")
    painter.blank(1)
    dots = []
    for answer in result.answers:
        color = "green" if answer.correct else ("peach" if answer.skipped else "red")
        dots.append(theme.paint("●", color))
    centered(painter, " ".join(dots))
    painter.blank(1)
    wrong = result.wrong_words
    if wrong:
        for line in term.wrap("错词已进错词本：" + " / ".join(wrong[:6]),
                              max(10, painter.width - 8), max_lines=2):
            centered(painter, line, "peach")
    else:
        centered(painter, "全部拼对，漂亮。", "green")
    painter.blank(1)
    due = next_due_label(session.states)
    if due != "-":
        centered(painter, "下次复习  " + due, "overlay1")

    _fit(painter, painter.height - 2)
    bottom_rule(painter)
    frame_footer(painter, [("⏎", "再来一组"), ("⇥", "进度"), ("esc/⌃c", "退出")])
    return painter.render()


def _render_help(painter: Painter, session: DrillSession) -> list[str]:
    theme = painter.theme
    painter.blank(1)
    centered(painter, "键盘", "mauve", bold=True)
    painter.blank(1)
    for key, label in HELP_LINES:
        painter.add(" " * 4 + theme.paint(f"{key:>6}", "lavender", bold=True)
                    + "   " + theme.paint(label, "subtext"))
    painter.blank(1)
    centered(painter, MODE_HINTS.get(session.mode, ""), "overlay1")
    painter.blank(1)
    centered(painter, "在 Herdr 里按 prefix+w 随时开始；Ctrl+C 也可以退出。", "surface2")
    while len(painter.rows) < painter.height - 1:
        painter.blank(1)
    bottom_rule(painter)
    frame_footer(painter, [("?", "关闭"), ("esc/⌃c", "退出")])
    return painter.render()


def _render_empty(painter: Painter, session: DrillSession) -> list[str]:
    hint = {
        "favorites": ("收藏夹还是空的",
                      "练到喜欢的词时按 Ctrl+F 收藏，之后就能在这里专练它。"),
        "review": ("错词本是空的",
                   "拼错的单词会自动进错词本，先随便练一组吧。"),
    }.get(session.mode, ("这个词书暂时没有可练的单词",
                         "换一本词书，或者导入自己的词表。"))

    painter.blank(2)
    centered(painter, hint[0], "text", bold=True)
    painter.blank(1)
    for line in term.wrap(hint[1], max(16, painter.width - 10), max_lines=2):
        centered(painter, line, "subtext")
    painter.blank(1)
    centered(painter, "换模式：  words drill -m smart", "overlay1")
    centered(painter, "换词书：  words books", "overlay1")
    _fit(painter, painter.height - 3)
    bottom_rule(painter)
    _render_status(painter, session, 0, 0, True)
    frame_footer(painter, [("esc/⌃c", "退出")])
    return painter.render()


# ---------------------------------------------------------------------------
# Input
# ---------------------------------------------------------------------------

class Keys:
    ESC = "esc"
    ENTER = "enter"
    TAB = "tab"
    BACKSPACE = "backspace"
    DELETE = "delete"
    CTRL_C = "ctrl-c"
    CTRL_R = "ctrl-r"
    CTRL_F = "ctrl-f"
    CTRL_M = "ctrl-m"
    CTRL_S = "ctrl-s"
    CTRL_L = "ctrl-l"
    UP = "up"
    DOWN = "down"
    LEFT = "left"
    RIGHT = "right"


KEY_BYTES = {
    b"\x1b": Keys.ESC, b"\r": Keys.ENTER, b"\n": Keys.ENTER, b"\t": Keys.TAB,
    b"\x7f": Keys.BACKSPACE, b"\x08": Keys.BACKSPACE, b"\x03": Keys.CTRL_C,
    b"\x12": Keys.CTRL_R, b"\x06": Keys.CTRL_F,
    b"\x13": Keys.CTRL_S, b"\x0c": Keys.CTRL_L,
}

ESCAPE_SEQUENCES = {
    b"\x1b[A": Keys.UP, b"\x1b[B": Keys.DOWN, b"\x1b[C": Keys.RIGHT,
    b"\x1b[D": Keys.LEFT, b"\x1b[3~": Keys.DELETE, b"\x1bOA": Keys.UP,
    b"\x1bOB": Keys.DOWN, b"\x1bOC": Keys.RIGHT, b"\x1bOD": Keys.LEFT,
}


def decode_keys(buffer: bytes) -> tuple[list[str], bytes]:
    """Split a byte buffer into key events and an undecoded remainder."""
    keys: list[str] = []
    index = 0
    length = len(buffer)
    while index < length:
        byte = buffer[index]
        if byte == 0x1B:
            matched = False
            for seq, name in sorted(ESCAPE_SEQUENCES.items(), key=lambda kv: -len(kv[0])):
                if buffer.startswith(seq, index):
                    keys.append(name)
                    index += len(seq)
                    matched = True
                    break
            if matched:
                continue
            if index + 1 >= length:
                break
            keys.append(Keys.ESC)
            index += 1
            continue
        name = KEY_BYTES.get(buffer[index:index + 1])
        if name:
            keys.append(name)
            index += 1
            continue
        if byte < 0x20:
            index += 1
            continue
        for size in range(1, 5):
            chunk = buffer[index:index + size]
            if len(chunk) < size:
                break
            try:
                char = chunk.decode("utf-8")
            except UnicodeDecodeError:
                continue
            keys.append(char)
            index += size
            break
        else:
            index += 1
    return keys, buffer[index:]


def flush_keys(buffer: bytes) -> tuple[list[str], bytes]:
    """Decode a buffer whose last key never got a follow-up byte.

    ``decode_keys`` holds a trailing ESC back because it may start a sequence
    like ``\x1b[A``. When nothing more arrives within a tick, that ESC really is
    the Escape key, so surface it instead of making the user press it twice.
    """
    keys, rest = decode_keys(buffer)
    guard = 0
    while rest.startswith(b"\x1b") and len(rest) < 8 and guard < 4:
        guard += 1
        keys.append(Keys.ESC)
        more, rest = decode_keys(rest[1:])
        keys.extend(more)
    return keys, rest


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


class RawTerminal:
    """Raw keyboard mode plus the smallest screen plumbing that always works.

    Alternate screen and synchronized output both look nicer in a full-screen
    terminal, but they are exactly the features a multiplexer's pane emulator
    may defer, which shows up as a permanently blank pane. So the defaults are
    the conservative ones: draw in place, clear behind us, restore the cursor.
    Opt in with WORDS_TUI_ALT_SCREEN=1 / WORDS_TUI_SYNC=1 when running in a
    terminal you control.
    """

    def __init__(self, probe: bool = True) -> None:
        self.probe = probe
        try:
            self.fd: int | None = sys.stdin.fileno()
        except (OSError, ValueError, AttributeError):
            self.fd = None
        self.saved = None
        self.alt_screen = _env_flag("WORDS_TUI_ALT_SCREEN")
        self.palette: str | None = None

    def __enter__(self) -> "RawTerminal":
        try:
            import termios
            import tty

            if self.fd is None:
                raise OSError("no terminal")
            self.saved = termios.tcgetattr(self.fd)
            tty.setraw(self.fd)
        except (ImportError, OSError, ValueError):
            self.saved = None
        # Probing is opt-in: a multiplexer pane does not answer OSC 11, and even
        # if it did, the default palette already works on both backgrounds.
        self.palette = (term.probe_background(self.fd)
                        if self.probe and self.saved and _env_flag("WORDS_THEME_PROBE")
                        else None)
        if self.palette:
            term.set_palette(self.palette)
        if self.alt_screen:
            term.emit("\x1b[?1049h")
        term.emit("\x1b[?25l\x1b[?7l\x1b[2J\x1b[H")
        return self

    def __exit__(self, *exc) -> None:
        # Restore the terminal and get out. No full-screen clear: in a herdr
        # popup the pane closes right after us, and asking the host to repaint
        # the whole viewport is what makes closing feel sticky.
        if self.alt_screen:
            term.emit("\x1b[0m\x1b[?7h\x1b[?25h\x1b[?1049l")
        else:
            term.emit("\x1b[0m\x1b[?7h\x1b[?25h\r\n")
        if self.saved is not None and self.fd is not None:
            try:
                import termios

                termios.tcsetattr(self.fd, termios.TCSADRAIN, self.saved)
            except (ImportError, OSError, ValueError):
                pass


class DrillApp:
    """Owns the render/input loop for one session."""

    def __init__(self, session: DrillSession, *, theme: Theme | None = None,
                 streak: int = 0, today_count: int = 0, daily_goal: int = 0,
                 sound_on: bool = True, on_pronounce=None, on_favorite=None,
                 on_master=None, on_toggle_sound=None, on_result=None,
                 autoplay: bool | str = False, input_fd: int | None = None,
                 output=None, palette: str = "auto"):
        self.session = session
        self.palette_mode = (palette or "auto").lower()
        if self.palette_mode not in {"dark", "light"}:
            self.palette_mode = "auto"
        self.theme = theme or Theme(palette=self.palette_mode)
        self.streak = streak
        self.today_count = today_count
        self.daily_goal = daily_goal
        self.sound_on = sound_on
        self.on_pronounce = on_pronounce
        self.on_favorite = on_favorite
        self.on_master = on_master
        self.on_toggle_sound = on_toggle_sound
        self.on_result = on_result
        self.autoplay = autoplay
        self.help_open = False
        self.message = ""
        self.message_until = 0.0
        self.flash_until = 0.0
        self.quit = False
        self.result: SessionResult | None = None
        if input_fd is not None:
            self.input_fd: int | None = input_fd
        else:
            try:
                self.input_fd = sys.stdin.fileno()
            except (OSError, ValueError, AttributeError):
                self.input_fd = None
        self.output = output or sys.stdout
        self._autoplay_at = 0.0
        self._autoplay_step = 0
        self._resized = False
        self._last_size = (0, 0)
        self._session_end_handled = False
        self.sync_output = _env_flag("WORDS_TUI_SYNC")

    def run(self) -> SessionResult | None:
        with RawTerminal(probe=self.palette_mode == "auto"):
            old_handler = signal.getsignal(signal.SIGWINCH)
            signal.signal(signal.SIGWINCH, self._on_resize)
            try:
                self._draw(force=True)
                buffer = b""
                while not self.quit:
                    now = time.time()
                    if self.flash_until and now >= self.flash_until:
                        self.flash_until = 0.0
                        if self.session.phase == "result":
                            self._advance()
                    if self.message_until and now >= self.message_until:
                        self.message = ""
                        self.message_until = 0.0
                    if self.autoplay and self.session.phase != "done" and now >= self._autoplay_at:
                        self._autoplay_tick()
                    if self._resized:
                        self._resized = False
                        self._draw(force=True)
                    timeout = 0.02 if self.autoplay and self.session.phase != "done" else TICK
                    if self.input_fd is None:
                        time.sleep(timeout)
                        self._draw()
                        continue
                    wait = ESCAPE_GRACE if buffer == b"\x1b" else timeout
                    ready, _, _ = select.select([self.input_fd], [], [], min(wait, timeout))
                    if not ready and buffer:
                        # Timeout with a dangling byte: it is a bare ESC.
                        keys, buffer = flush_keys(buffer)
                        for key in keys:
                            self._handle(key)
                            if self.quit:
                                break
                            self._draw()
                        continue
                    if ready:
                        try:
                            chunk = os.read(self.input_fd, 64)
                        except OSError:
                            break
                        if not chunk:
                            break
                        buffer += chunk
                        keys, buffer = decode_keys(buffer)
                        for key in keys:
                            self._handle(key)
                            if self.quit:
                                break
                            self._draw()
            finally:
                signal.signal(signal.SIGWINCH, old_handler)
        return self.result

    def _on_resize(self, *_args) -> None:
        self._resized = True

    # -- input handling --------------------------------------------------
    def _handle(self, key: str) -> None:
        session = self.session
        if key == Keys.CTRL_C:
            self.quit = True
            return
        if self.help_open:
            if key in {"?", Keys.ESC, Keys.ENTER}:
                self.help_open = False
                self._draw(force=True)
            return
        if key == "?":
            self.help_open = True
            self._draw(force=True)
            return
        if key == Keys.ESC:
            self.quit = True
            return
        if key == Keys.CTRL_R:
            self._pronounce()
            return
        if key == Keys.CTRL_F:
            if self.on_favorite is not None and session.current:
                fav = self.on_favorite(session.current)
                self._flash(f"{'已收藏' if fav else '已取消收藏'}  {session.current.word}")
            return
        if key == Keys.CTRL_M:
            if self.on_master is not None and session.current:
                self.on_master(session.current)
                self._flash(f"已标记掌握  {session.current.word}")
            return
        if key == Keys.CTRL_S:
            self.sound_on = not self.sound_on
            if self.on_toggle_sound is not None:
                self.on_toggle_sound(self.sound_on)
            self._flash("声音已开" if self.sound_on else "声音已关")
            return

        if session.phase == "done":
            if key == Keys.ENTER and self.on_result is not None:
                self.on_result(session.result(), "again")
            elif key == Keys.TAB and self.on_result is not None:
                self.on_result(session.result(), "stats")
            return

        if session.phase == "result":
            if key in {Keys.ENTER, " ", Keys.TAB}:
                self.flash_until = 0.0
                self._advance()
            return

        if session.mode == "selfcheck":
            if key in {"1", "2", "3", "4"}:
                self._self_grade(int(key))
            return
        if key == Keys.ENTER:
            if session.typed:
                self._submit()
            else:
                self._flash("先输入字母，或用 esc 退出", "peach")
            return
        if key == Keys.TAB:
            revealed = session.hint()
            self._flash(f"提示：{revealed}" if revealed else "没有更多提示了", "peach")
            return
        if key == Keys.BACKSPACE:
            session.backspace()
            return
        if key == Keys.DELETE:
            session.clear_typed()
            return
        if len(key) == 1 and key.isprintable():
            if session.type_char(key):
                self._after_submit()

    def _submit(self) -> None:
        if self.session.submit() is not None:
            self._after_submit()

    def _self_grade(self, raw: int) -> None:
        quality = {1: 1, 2: 3, 3: 4, 4: 5}[raw]
        if self.session.self_grade(quality) is not None:
            self._after_submit()

    def _after_submit(self) -> None:
        answer = self.session.last_answer
        if answer is None:
            return
        if answer.correct:
            self._pronounce()
        self.flash_until = time.time() + (RESULT_HOLD_OK if answer.correct else RESULT_HOLD_BAD)
        self.today_count += 1
        self._draw(force=True)

    def _advance(self) -> None:
        session = self.session
        more = session.advance()
        if not more:
            self.result = session.result()
            if not self._session_end_handled and self.on_result is not None:
                self._session_end_handled = True
                self.on_result(self.result, "finish")
        self._draw(force=True)

    def _pronounce(self) -> None:
        if self.on_pronounce is not None and self.session.current and self.sound_on:
            self.on_pronounce(self.session.current)

    def _flash(self, text: str, color: str = "teal") -> None:
        self.message = text
        self.message_until = time.time() + 1.6
        self._draw(force=True)

    # -- autoplay used by tests -------------------------------------------
    def _autoplay_tick(self) -> None:
        session = self.session
        if session.phase == "done":
            return
        if session.phase == "typing":
            word = session.current
            if word is None:
                return
            if session.mode == "selfcheck":
                self._self_grade(3)
                return
            target = word.word
            step = self._autoplay_step
            if self.autoplay == "sloppy" and step == 0 and session.index % 3 == 1:
                session.type_char("z")
                session.backspace()
            if step >= len(target):
                self._submit()
                self._autoplay_step = 0
                return
            session.type_char(target[step])
            self._autoplay_step = step + 1
            if session.phase == "result":
                self._autoplay_step = 0
                self.flash_until = 0.0
                self._advance()
        self._autoplay_at = time.time() + 0.015

    # -- drawing ---------------------------------------------------------
    def _draw(self, force: bool = False) -> None:
        width, height = term.terminal_size()
        if not force and (width, height) == self._last_size and not self.flash_until:
            return
        self._last_size = (width, height)
        lines = render_drill(
            self.session, self.theme, width, height,
            streak=self.streak, today_count=self.today_count,
            daily_goal=self.daily_goal, sound_on=self.sound_on,
            help_open=self.help_open, message=self.message,
        )
        # One self-contained frame: home, paint, erase the rest, done. Sync
        # mode, when enabled, wraps this frame and is closed before returning,
        # so a pane emulator that defers synchronized updates still ends up
        # with a committed screen.
        frame = "\x1b[H" + "\r\n".join(lines) + "\x1b[J"
        if self.sync_output:
            self.output.write("\x1b[?2026h" + frame + "\x1b[?2026l")
        else:
            self.output.write(frame)
        self.output.flush()
