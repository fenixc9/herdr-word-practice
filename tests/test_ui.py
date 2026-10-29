import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from worddrill import term  # noqa: E402
from worddrill.data import Word  # noqa: E402
from worddrill.session import DrillSession  # noqa: E402
from worddrill.ui import (DrillApp, Theme, decode_keys, flush_keys,  # noqa: E402
                          render_drill)


def make_word(name="cache", cn="缓存", pos="n.") -> Word:
    return Word(key=f"b:{name}", book="b", word=name, ipa="/kæʃ/", pos=pos,
                cn=cn, en="The cache hides latency.", zh="缓存掩盖了延迟。",
                syn=("store", "buffer"), root="cach（藏）")


def session_for(words, mode="follow") -> DrillSession:
    return DrillSession(words=list(words), mode=mode, book_label="测试词书")


def frame(session, width=80, height=24, **kwargs):
    kwargs.setdefault("book_name", "测试词书")
    kwargs.setdefault("total_words", 340)
    return render_drill(session, Theme(), width, height, **kwargs)


def test_every_line_is_exactly_the_requested_width():
    session = session_for([make_word()])
    for width in (56, 70, 80, 100):
        for line in frame(session, width=width, height=20):
            assert term.text_width(line) == width, f"width mismatch at {width}: {line!r}"


def test_frame_height_is_respected():
    session = session_for([make_word()])
    assert len(frame(session, width=80, height=18)) == 18
    assert len(frame(session, width=80, height=30)) == 30


def test_card_shows_word_phonetics_and_meaning_in_follow_mode():
    session = session_for([make_word()])
    text = term.strip_ansi("\n".join(frame(session)))
    assert "cache" in text
    assert "/kæʃ/" in text
    assert "缓存" in text
    assert "1/1" in text


def test_dictation_hides_the_word_but_shows_the_gap():
    session = session_for([make_word()], mode="dictation")
    text = term.strip_ansi("\n".join(frame(session)))
    assert "cache" not in text.replace("hides latency", "")
    assert "_ _ _ _ _" in text
    assert "缓存" in text


def test_selfcheck_shows_grading_keys():
    session = session_for([make_word()], mode="selfcheck")
    text = term.strip_ansi("\n".join(frame(session)))
    assert "不认识" in text and "模糊" in text and "认识" in text
    assert "1-4" in text


def test_result_phase_shows_verdict_and_answer():
    session = session_for([make_word()], mode="dictation")
    for char in "cachx":
        session.type_char(char)
    session.submit()
    text = term.strip_ansi("\n".join(frame(session)))
    assert "拼写错误" in text
    assert "cache" in text
    assert "cachx" in text


def test_summary_phase_reports_accuracy():
    session = session_for([make_word()], mode="follow")
    for char in "cache":
        session.type_char(char)
    session.advance()
    text = term.strip_ansi("\n".join(frame(session)))
    assert "训练完成" in text
    assert "100%" in text


def test_empty_session_explains_itself():
    session = session_for([], mode="review")
    text = term.strip_ansi("\n".join(frame(session)))
    assert "错词本是空的" in text
    assert "words drill -m smart" in text
    assert "100%" not in text, "an empty session has no progress to celebrate"


def test_help_overlay_lists_shortcuts():
    session = session_for([make_word()])
    text = term.strip_ansi("\n".join(frame(session, help_open=True)))
    for key in ("Tab", "Enter", "Ctrl+B", "Ctrl+K"):
        assert key in text


def test_status_bar_tracks_progress_and_goal():
    session = session_for([make_word("a"), make_word("b")], mode="follow")
    for char in "a":
        session.type_char(char)
    session.advance()
    text = term.strip_ansi("\n".join(frame(session, streak=4, today_count=7, daily_goal=20)))
    assert "50%" in text
    assert "今日 7/20" in text
    assert "4" in text


def test_decode_keys_handles_utf8_and_escapes():
    keys, rest = decode_keys("é".encode())
    assert keys == ["é"] and rest == b""
    keys, rest = decode_keys(b"\x1b[A\x1b")
    assert keys == ["up"]
    assert rest == b"\x1b", "a lone escape byte is held back for the next read"
    keys, rest = decode_keys(b"ab\t\r\x7f")
    assert keys == ["a", "b", "tab", "enter", "backspace"]


def test_decode_keys_handles_ctrl_combinations():
    keys, _ = decode_keys(b"\x03\x02\x0b")
    assert keys == ["ctrl-c", "ctrl-b", "ctrl-k"]
    # Ctrl+M arrives as a bare CR, which is indistinguishable from Enter
    assert decode_keys(b"\r")[0] == ["enter"]


def test_flush_keys_turns_a_dangling_escape_into_esc():
    keys, rest = flush_keys(b"a\x1b")
    assert keys == ["a", "esc"] and rest == b""
    keys, rest = flush_keys(b"\x1b\x1b")
    assert keys == ["esc", "esc"] and rest == b""
    keys, rest = flush_keys(b"\x1b[")
    assert keys[0] == "esc", "a partial sequence degrades to Escape plus text"


def test_painter_pads_and_truncates():
    from worddrill.ui import Painter

    painter = Painter(10, 3, Theme())
    painter.add("hello")
    painter.add("x" * 30)
    rows = painter.render()
    assert len(rows) == 3
    assert all(term.text_width(row) == 10 for row in rows)


def test_app_tolerates_a_pseudofile_stdin(monkeypatch):
    session = session_for([make_word()])
    app = DrillApp(session, autoplay=False)
    assert app.input_fd is None, "no fileno available under pytest capture"
    assert session.phase == "typing"


def test_theme_colors_can_be_disabled(monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    assert term.color_supported() is False


# Glyphs whose width depends on the font. In a CJK locale '·' and '—' are often
# rendered two cells wide, which silently pushes frame edges out of alignment.
FORBIDDEN_IN_LAYOUT = "\u00b7\u2014\u2026\u201c\u201d\u2018\u2019\u2192\u25cf"
BOX_DRAWING = set("─│┌┐└┘├┤┬┴┼╭╮╰╯╱╲╳▁▂▃▄▅▆▇█▉▊▋▌▍▎▏▐░▒▓▔▕")


def test_layout_rows_avoid_ambiguous_width_glyphs():
    """Only structural rows must be glyph-safe.

    The card body legitimately contains IPA such as ``æ`` (ambiguous width by the
    Unicode table). Structural rows — header, status bar, footer — must stick to
    glyphs every font draws one cell wide, otherwise the frame edges drift.
    """
    session = session_for([make_word()], mode="dictation")
    session.typed = "cachx"
    session.submit()
    lines = frame(session, width=72, height=22)
    structural = [lines[0], lines[-2], lines[-1]]
    for line in structural:
        plain = term.strip_ansi(line)
        for char in FORBIDDEN_IN_LAYOUT:
            assert char not in plain, f"ambiguous-width glyph {char!r} in {plain!r}"
        # Box drawing and blocks are "ambiguous" by the Unicode table but are
        # one cell in every terminal font, so they are allowed.
        for char in plain:
            if char.isascii() or char in BOX_DRAWING:
                continue
            width = term.unicodedata.east_asian_width(char)
            assert width in {"W", "F", "N", "H"}, (
                f"{char!r} has ambiguous width ({width}); must not be used in layout")


def test_footer_corner_sits_on_the_frame_edge():
    session = session_for([make_word()])
    for width in (56, 72, 96):
        lines = [term.strip_ansi(line).rstrip() for line in frame(session, width=width, height=20)]
        footer = lines[-1]
        assert footer.endswith("─╯"), footer
        assert term.text_width(footer) == width
        # the corner must be the last cell, i.e. directly under the header's ╮
        assert term.text_width(lines[0]) == width


def test_status_bar_shows_today_total_and_book():
    session = session_for([make_word("cache"), make_word("deploy")], mode="follow")
    session.typed = "cache"
    session.submit()
    session.advance()
    text = term.strip_ansi("\n".join(
        frame(session, width=76, height=18, streak=3, today_count=8,
              daily_goal=20))).splitlines()[-2]
    assert "今日 8/20" in text
    assert "累计 340 词" in text
    assert "CET-4 核心" in text or "测试词书" in text
    assert term.text_width(text) == 76


def test_status_bar_drops_the_tail_not_the_numbers():
    session = session_for([make_word()])
    for width in (44, 50, 60):
        text = term.strip_ansi("\n".join(
            frame(session, width=width, height=18, today_count=8,
                  daily_goal=20))).splitlines()[-2]
        assert "今日 8/20" in text, f"today count lost at width {width}: {text!r}"
        assert "累计" in text, f"total lost at width {width}: {text!r}"


def test_status_bar_never_slices_a_segment():
    """Every segment is dropped whole; nothing is cut mid-glyph."""
    session = session_for([make_word("illustrate")])
    for width in range(40, 121, 2):
        lines = frame(session, width=width, height=18,
                      today_count=12, daily_goal=20)
        row = term.strip_ansi(lines[-2])
        assert term.text_width(row) == width, f"ragged row at width {width}: {row!r}"
        assert row.endswith("│")
        for clock in ("00:0", "00:"):
            assert not row.rstrip("│ ").endswith(clock), f"cut clock at {width}: {row!r}"
