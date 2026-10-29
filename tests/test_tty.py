"""End-to-end test of the interactive drill through a real pty.

The TUI only runs when stdin is a terminal, so this test allocates one, types a
word like a user would, and then checks that the answer landed in progress.json.
"""

import fcntl
import json
import os
import pty
import re
import select
import struct
import subprocess
import sys
import termios
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
MAIN = ROOT / "main.py"
ANSI = re.compile(r"\x1b\[[0-9;?]*[a-zA-Z]|\x1b\][^\x07]*\x07")

pytestmark = pytest.mark.skipif(not sys.platform.startswith("linux"),
                                reason="pty helpers are POSIX only")


def _strip(data: bytes) -> str:
    return ANSI.sub("", data.decode("utf-8", "replace"))


class Tui:
    def __init__(self, env: dict, args: list[str], columns: int = 100,
                 rows: int = 30) -> None:
        self.master, slave = pty.openpty()
        window = struct.pack("HHHH", rows, columns, 0, 0)
        fcntl.ioctl(slave, termios.TIOCSWINSZ, window)
        self.proc = subprocess.Popen(
            [sys.executable, str(MAIN), *args],
            cwd=str(ROOT), env=env, stdin=slave, stdout=slave, stderr=slave,
            start_new_session=True, close_fds=True,
        )
        os.close(slave)
        self.buffer = b""

    def read_until(self, predicate, timeout: float = 10.0) -> str:
        deadline = time.time() + timeout
        while time.time() < deadline:
            ready, _, _ = select.select([self.master], [], [], 0.1)
            if ready:
                try:
                    chunk = os.read(self.master, 65536)
                except OSError:
                    break
                if not chunk:
                    break
                self.buffer += chunk
                text = _strip(self.buffer)
                if predicate(text):
                    return text
            if self.proc.poll() is not None:
                break
        return _strip(self.buffer)

    def send(self, keys: str) -> None:
        os.write(self.master, keys.encode())

    def close(self) -> None:
        try:
            self.proc.terminate()
            self.proc.wait(timeout=5)
        except (subprocess.TimeoutExpired, ProcessLookupError):
            self.proc.kill()
        finally:
            try:
                os.close(self.master)
            except OSError:
                pass


@pytest.fixture()
def env(tmp_path):
    environment = dict(os.environ)
    environment["HERDR_PLUGIN_STATE_DIR"] = str(tmp_path / "state")
    environment["HERDR_PLUGIN_CONFIG_DIR"] = str(tmp_path / "config")
    environment["TERM"] = "xterm-256color"
    return environment


@pytest.fixture()
def one_word_book(tmp_path, env):
    source = tmp_path / "one.tsv"
    source.write_text("# id=one\n# name=一个词\ncache\t/kæʃ/\tn.\t缓存\n",
                      encoding="utf-8")
    subprocess.run([sys.executable, str(MAIN), "import", str(source)],
                   cwd=str(ROOT), env=env, check=True, capture_output=True)
    return tmp_path / "state" / "progress.json"


def test_typing_the_word_records_progress(one_word_book, env):
    tui = Tui(env, ["drill", "-b", "one", "-n", "1", "-m", "follow", "--no-sound"])
    try:
        screen = tui.read_until(lambda text: "cache" in text)
        assert "cache" in screen, f"card never rendered:\n{screen}"
        assert "缓存" in screen

        tui.send("cachx")          # a typo first
        tui.read_until(lambda text: "拼写错误" in text)
        tui.send("\r")             # accept the miss and move on
        summary = tui.read_until(lambda text: "训练完成" in text)
        assert "训练完成" in summary
        tui.send("\x1b")           # quit from the summary screen
        assert tui.proc.wait(timeout=10) == 0
    finally:
        tui.close()

    progress = json.loads(one_word_book.read_text())
    state = progress["words"]["one:cache"]
    assert state["wrong"] == 1
    assert state["status"] == "learning", "a miss sends the word back to learning"
    assert progress["days"], "daily stats should be recorded"
    day = list(progress["days"].values())[0]
    assert day["wrong"] == 1
    assert day["new"] == 1


def test_correct_typing_auto_advances(one_word_book, env):
    tui = Tui(env, ["drill", "-b", "one", "-n", "1", "-m", "dictation",
                    "--no-sound"])
    try:
        screen = tui.read_until(lambda text: "_ _ _ _ _" in text)
        assert "_ _ _ _ _" in screen, f"masked prompt missing:\n{screen}"
        for char in "cache":
            tui.send(char)
            time.sleep(0.03)
        summary = tui.read_until(lambda text: "训练完成" in text)
        assert "100%" in summary
        tui.send("\x1b")           # quit straight from the summary screen
        assert tui.proc.wait(timeout=10) == 0
    finally:
        tui.close()

    progress = json.loads(one_word_book.read_text())
    state = progress["words"]["one:cache"]
    assert state["correct"] == 1
    assert state["wrong"] == 0
    assert state["due"] > 0
    day = list(progress["days"].values())[0]
    assert day["correct"] == 1
    assert day["sessions"] == 1, "finishing a session is counted"


def test_hint_key_reveals_a_prefix(one_word_book, env):
    tui = Tui(env, ["drill", "-b", "one", "-n", "1", "-m", "spelling",
                    "--no-sound"])
    try:
        tui.read_until(lambda text: "_ _ _ _ _" in text)
        tui.send("\t")
        screen = tui.read_until(lambda text: "c" in text)
        assert "c" in screen
        tui.send("\x1b\x1b")       # double escape: quit
        tui.proc.wait(timeout=10)
    finally:
        tui.close()


def test_quit_leaves_state_writable(one_word_book, env):
    tui = Tui(env, ["drill", "-b", "one", "-n", "1", "-m", "follow", "--no-sound"])
    try:
        tui.read_until(lambda text: "cache" in text)
        tui.send("\x1b")
        assert tui.proc.wait(timeout=10) == 0
    finally:
        tui.close()
    assert not one_word_book.exists() or isinstance(
        json.loads(one_word_book.read_text()), dict)


def test_stats_pane_waits_for_enter(tmp_path, env):
    tui = Tui(env, ["stats", "--wait"])
    try:
        screen = tui.read_until(lambda text: "最近 7 天" in text)
        assert "记忆状态" in screen
        assert "最近 7 天" in screen
        assert "待复习" in screen
        tui.send("\r")
        assert tui.proc.wait(timeout=10) == 0
    finally:
        tui.close()


def test_enter_on_summary_starts_another_session(one_word_book, env):
    tui = Tui(env, ["drill", "-b", "one", "-n", "1", "-m", "follow", "--no-sound"])
    try:
        tui.read_until(lambda text: "cache" in text)
        tui.send("cache")
        tui.read_until(lambda text: "训练完成" in text)
        tui.send("\r")                      # 再来一组
        again = tui.read_until(lambda text: "1/1" in text, timeout=8)
        assert "1/1" in again, f"a new session should start:\n{again}"
        tui.send("\x1b")
        tui.proc.wait(timeout=10)
    finally:
        tui.close()
    progress = json.loads(one_word_book.read_text())
    day = list(progress["days"].values())[0]
    assert day["sessions"] >= 2, "finishing and restarting are both counted"
    assert progress["words"]["one:cache"]["correct"] == 1


def test_background_probe_switches_the_palette(tmp_path, env):
    """If the terminal answers OSC 11 with white, the TUI must use light colors."""
    import pty as _pty

    script = tmp_path / "probe.py"
    script.write_text(
        "import sys; sys.path.insert(0, %r)\n"
        "from worddrill import term\n"
        "import tty; tty.setraw(0)\n"
        "print('PALETTE=' + str(term.probe_background(0, timeout=2.0)))\n"
        "raise SystemExit(0)\n" % str(ROOT))
    master, slave = _pty.openpty()
    proc = subprocess.Popen([sys.executable, str(script)], stdin=slave,
                            stdout=slave, stderr=slave, env=env,
                            start_new_session=True)
    os.close(slave)
    query = b""
    deadline = time.time() + 5
    while time.time() < deadline and b"\x1b]11;?" not in query:
        ready, _, _ = select.select([master], [], [], 0.2)
        if ready:
            query += os.read(master, 256)
    os.write(master, b"\x1b]11;rgb:ffff/ffff/ffff\x07")
    output = b""
    while time.time() < deadline:
        ready, _, _ = select.select([master], [], [], 0.2)
        if ready:
            try:
                chunk = os.read(master, 4096)
            except OSError:
                break
            if not chunk:
                break
            output += chunk
        if proc.poll() is not None:
            break
    proc.wait(timeout=5)
    os.close(master)
    assert b"PALETTE=light" in output, output
