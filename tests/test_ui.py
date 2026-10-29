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
