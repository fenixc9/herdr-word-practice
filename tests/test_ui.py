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
    session = session_for([], mode="favorites")
    text = term.strip_ansi("\n".join(frame(session)))
    assert "收藏夹还是空的" in text
    assert "Ctrl+F" in text
    assert "words drill -m smart" in text
    assert "100%" not in text, "an empty session has no progress to celebrate"


def test_help_overlay_lists_shortcuts():
    session = session_for([make_word()])
    text = term.strip_ansi("\n".join(frame(session, help_open=True)))
    for key in ("Tab", "Enter", "Ctrl+F", "Ctrl+M"):
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
    keys, _ = decode_keys(b"\x12\x06\x13")
    assert keys == ["ctrl-r", "ctrl-f", "ctrl-s"]
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


def test_pronunciation_providers_switch_accent(monkeypatch):
    from worddrill import audio

    monkeypatch.delenv("WORDDRILL_NO_AUDIO", raising=False)
    monkeypatch.delenv("WORDDRILL_SAY", raising=False)
    calls = []

    def fake_popen(argv, **kwargs):
        calls.append(argv)
        return object()

    monkeypatch.setattr(audio.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(audio.shutil, "which", lambda name: f"/usr/bin/{name}")
    assert audio.pronounce(make_word(), accent="uk") is True
    assert calls and calls[-1][-1] == "cache"


def test_audio_disabled_by_env(monkeypatch):
    from worddrill import audio

    monkeypatch.setenv("WORDDRILL_NO_AUDIO", "1")
    assert audio.find_provider() is None
    assert audio.pronounce(make_word()) is False


def test_herdr_error_payloads_are_read_from_stderr(monkeypatch):
    from worddrill import herdr

    class FakeProc:
        returncode = 1
        stdout = ""
        stderr = '{"error":{"code":"ui_busy","message":"a popup pane is already open"}}'

    monkeypatch.setenv("HERDR_ENV", "1")
    monkeypatch.setattr(herdr.subprocess, "run", lambda *a, **k: FakeProc())
    assert herdr.run_herdr(["plugin", "pane", "open"]) is None
    _, error = herdr.open_pane_detailed("break")
    assert error == "ui_busy"


def test_result_card_shows_collocations_and_etymology():
    word = Word(key="b:deploy", book="b", word="deploy", ipa="/dɪˈplɔɪ/", pos="v.",
                cn="部署", en="We deploy twice a day.", zh="我们每天部署两次。",
                syn=("release",), root="de-（去掉）+ ploy（折叠）",
                phr=("deploy to production", "roll out a release"))
    session = DrillSession(words=[word], mode="dictation")
    session.typed = "deploi"
    session.submit()
    text = term.strip_ansi("\n".join(frame(session, height=26)))
    assert "deploy to production" in text
    assert "de-（去掉）" in text
    assert "近义" in text


def test_palettes_have_the_same_keys_and_contrast():
    dark, light = term.HEX_DARK, term.HEX_LIGHT
    assert set(dark) == set(light)
    # Text must contrast with its own background in each palette.
    assert term.luminance(dark["text"]) > 0.5
    assert term.luminance(light["text"]) < 0.2
    assert term.luminance(term.HEX_LIGHT["base"]) > 0.8


def test_osc11_replies_choose_the_right_palette():
    assert term.parse_osc11(b"\x1b]11;rgb:1e1e/1e1e/2e2e\x07") == "dark"
    assert term.parse_osc11(b"\x1b]11;rgb:ffff/ffff/ffff\x1b\\") == "light"
    assert term.parse_osc11(b"\x1b]11;rgb:0000/0000/0000\x07") == "dark"
    assert term.parse_osc11(b"no reply here") is None


def test_probe_returns_none_without_a_terminal():
    assert term.probe_background(None) is None


def test_theme_switches_the_module_palette():
    Theme(palette="light")
    assert term.PALETTE == "light" and term.HEX["green"] == term.HEX_LIGHT["green"]
    Theme(palette="dark")
    assert term.PALETTE == "dark" and term.HEX["green"] == term.HEX_DARK["green"]
    Theme(palette="auto")
    assert term.PALETTE == "auto" and term.HEX["green"] == term.HEX_UNIVERSAL["green"]


def test_structural_colors_use_the_terminal_default_foreground():
    rendered = term.style("word", "text")
    assert rendered == "word", "body text must not carry a fixed color"
    assert "\x1b[38" not in rendered
    assert term.style("hint", "subtext").startswith("\x1b[2m"), "hierarchy via dim"


def test_default_accents_survive_both_backgrounds():
    def contrast(a, b):
        hi, lo = sorted((term.luminance(a), term.luminance(b)), reverse=True)
        return (hi + 0.05) / (lo + 0.05)

    for name in ("green", "red", "peach", "teal", "mauve", "blue", "yellow"):
        color = term.HEX_UNIVERSAL[name]
        assert contrast(color, "#1e1e2e") > 3.0, f"{name} too dark on dark bg"
        assert contrast(color, "#ffffff") > 3.0, f"{name} too pale on light bg"


def test_draw_does_not_leave_synchronized_output_open():
    import io

    session = session_for([make_word()])
    out = io.StringIO()
    app = DrillApp(session, output=out, input_fd=None)
    app._draw(force=True)
    text = out.getvalue()
    assert "herdr words" in term.strip_ansi(text)
    assert text.count("\x1b[?2026h") == text.count("\x1b[?2026l"), "sync must be balanced"
    assert text.endswith("\x1b[?2026l") or "\x1b[?2026h" not in text
    assert "\x1b[?1049h" not in text, "alt screen is opt-in only"


def test_sync_mode_wraps_each_frame_when_enabled(monkeypatch):
    import io

    session = session_for([make_word()])
    out = io.StringIO()
    app = DrillApp(session, output=out, input_fd=None)
    app.sync_output = True
    app._draw(force=True)
    text = out.getvalue()
    assert text.startswith("\x1b[?2026h")
    assert text.endswith("\x1b[?2026l")


def test_input_box_edges_line_up():
    session = session_for([make_word()])
    lines = [term.strip_ansi(line) for line in frame(session, width=70, height=18)]
    box = [line for line in lines if "输入" in line or line.strip().startswith("│ ") or "╰" in line]
    widths = {term.text_width(line.rstrip()) for line in box[:3]}
    assert len(widths) == 1, f"input box edges differ: {sorted(widths)}"
    left_edges = {len(line) - len(line.lstrip(" ")) for line in box[:3]}
    assert len(left_edges) == 1, f"input box left edges differ: {left_edges}"


def test_header_and_footer_close_the_frame():
    session = session_for([make_word()])
    for width in (52, 70, 100):
        lines = [term.strip_ansi(line).rstrip() for line in frame(session, width=width, height=20)]
        assert term.text_width(lines[0]) == width, "header must span the frame"
        assert lines[0].endswith("╮")
        assert term.text_width(lines[-1]) == width
        assert lines[-1].endswith("─╯"), f"footer must close the frame: {lines[-1]!r}"


def test_footer_keeps_quit_hint_when_space_is_tight():
    session = session_for([make_word()])
    for width in (34, 44, 56):
        lines = [term.strip_ansi(line).rstrip() for line in frame(session, width=width, height=20)]
        assert "esc" in lines[-1], f"quit hint dropped at width {width}: {lines[-1]!r}"
        assert term.text_width(lines[-1]) == width


def test_no_line_is_wider_than_the_frame():
    for mode in ("follow", "dictation", "spelling", "selfcheck"):
        session = session_for([make_word()], mode=mode)
        for width in (40, 48, 60):
            for line in frame(session, width=width, height=22):
                assert term.text_width(line) == width


def test_cjk_and_ascii_columns_align():
    """Rows padded by display width, not character count."""
    from worddrill.cli import _book_rows
    from worddrill.store import Progress
    from pathlib import Path as _Path
    import tempfile

    book = __import__("worddrill.data", fromlist=["find_book"]).find_book("cet4")
    coding = __import__("worddrill.data", fromlist=["find_book"]).find_book("coding")
    with tempfile.TemporaryDirectory() as tmp:
        progress = Progress.load(_Path(tmp))
        rows = [_book_rows(b, progress, False)[0] for b in (book, coding)]
    starts = set()
    for row in rows:
        plain = term.strip_ansi(row)
        starts.add(term.text_width(plain[: plain.index("共")]))
    assert len(starts) == 1, f"detail columns differ: {starts}"
