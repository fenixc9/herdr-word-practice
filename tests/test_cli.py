import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
MAIN = ROOT / "main.py"


@pytest.fixture()
def env(tmp_path):
    environment = dict(os.environ)
    environment["HERDR_PLUGIN_STATE_DIR"] = str(tmp_path / "state")
    environment["HERDR_PLUGIN_CONFIG_DIR"] = str(tmp_path / "config")
    environment["NO_COLOR"] = "1"
    environment.pop("HERDR_PLUGIN_EVENT_JSON", None)
    environment.pop("HERDR_PLUGIN_EVENT", None)
    return environment


def run(args, env, **kwargs):
    return subprocess.run([sys.executable, str(MAIN), *args],
                          cwd=str(ROOT), env=env, capture_output=True,
                          text=True, timeout=60, **kwargs)


def test_help_and_version(env):
    result = run(["--help"], env)
    assert result.returncode == 0
    for command in ("drill", "stats", "books", "import", "settings", "event",
                    "doctor"):
        assert command in result.stdout
    version = run(["--version"], env)
    assert version.returncode == 0 and version.stdout.startswith("words ")


def test_doctor_reports_environment(env):
    result = run(["doctor", "--json"], env)
    payload = json.loads(result.stdout)
    checks = {item["check"]: item["ok"] for item in payload}
    assert checks["python"] is True
    assert checks["wordbooks"] is True


def test_books_lists_all_bundled_books(env):
    payload = json.loads(run(["books", "--json"], env).stdout)
    ids = [book["id"] for book in payload]
    assert ids == ["cet4", "cet6", "coding"]
    assert payload[0]["size"] > 250
    assert payload[0]["sample"], "should show a few sample words"


def test_plan_outputs_words_without_touching_progress(env, tmp_path):
    result = run(["drill", "--plan", "--json", "-n", "5", "-m", "follow"], env)
    payload = json.loads(result.stdout)
    assert payload["book"] == "cet4"
    assert len(payload["words"]) == 5
    assert all(item["word"] and item["cn"] for item in payload["words"])
    assert not (tmp_path / "state" / "progress.json").exists()


def test_once_renders_a_frame(env):
    result = run(["drill", "--once", "-n", "3", "--width", "70", "--height", "20"], env)
    assert result.returncode == 0
    lines = result.stdout.splitlines()
    assert len(lines) == 20
    assert "word practice" in lines[0]


def test_stats_json_on_a_fresh_install(env):
    payload = json.loads(run(["stats", "--json"], env).stdout)
    assert payload["today"] == 0
    assert payload["streak"] == 0
    assert payload["status"]["new"] > 1000
    assert len(payload["days"]) == 7
    assert [book["id"] for book in payload["books"]] == ["cet4", "cet6", "coding"]


def test_stats_plain_output_has_sections(env):
    result = run(["stats"], env)
    assert result.returncode == 0
    assert "记忆状态" in result.stdout
    assert "最近 7 天" in result.stdout


def test_settings_roundtrip_from_the_cli(env, tmp_path):
    result = run(["settings", "book=coding", "session_size=6",
                  "nudge.min_gap_minutes=15"], env)
    assert result.returncode == 0
    stored = json.loads((tmp_path / "config" / "settings.json").read_text())
    assert stored["book"] == "coding"
    assert stored["session_size"] == 6
    assert stored["nudge"]["min_gap_minutes"] == 15
    assert stored["nudge"]["quiet_hours"] == [23, 8]

    plan = json.loads(run(["drill", "--plan", "--json"], env).stdout)
    assert plan["book"] == "coding", "settings should drive the default book"
    assert len(plan["words"]) == 6, "settings should drive the default size"


def test_settings_accept_json_values(env, tmp_path):
    result = run(["settings", "nudge.quiet_hours=[22,7]", "sound=false"], env)
    assert result.returncode == 0
    stored = json.loads((tmp_path / "config" / "settings.json").read_text())
    assert stored["nudge"]["quiet_hours"] == [22, 7]
    assert stored["sound"] is False


def test_bad_setting_is_ignored(env):
    result = run(["settings", "nonsense"], env)
    assert result.returncode == 0
    assert "忽略无效设置" in result.stderr


def test_unknown_book_fails_cleanly(env):
    result = run(["drill", "--plan", "-b", "nope"], env)
    assert result.returncode == 1
    assert "词书错误" in result.stderr


def test_import_then_use_custom_book(env, tmp_path):
    source = tmp_path / "custom.tsv"
    source.write_text(
        "# id=custom\n# name=我的词\ncache\t\tv.\t缓存\nschema\t\tv.\t表结构\n",
        encoding="utf-8")
    result = run(["import", str(source), "--use"], env)
    assert result.returncode == 0, result.stderr
    assert "2 个单词" in result.stdout
    plan = json.loads(run(["drill", "--plan", "--json", "-n", "2"], env).stdout)
    assert plan["book"] == "custom"
    assert {item["word"] for item in plan["words"]} == {"cache", "schema"}


def test_reset_requires_confirmation(env, monkeypatch):
    result = run(["reset"], env)
    assert result.returncode == 2
    assert run(["reset", "--yes"], env).returncode == 0


def test_event_without_payload_reports_error(env):
    result = run(["event"], env)
    assert result.returncode == 1
    assert "no event payload" in result.stderr


def quiet_hours_that_exclude_now() -> list[int]:
    """A quiet window that cannot contain the current hour (tests are not
    allowed to depend on what time the suite is run at)."""
    import time
    hour = time.localtime().tm_hour
    other = (hour + 2) % 24
    return [other, (other + 1) % 24]


def test_event_nudges_when_agent_goes_idle(env, tmp_path):
    run(["settings", f"nudge.quiet_hours={quiet_hours_that_exclude_now()}"], env)
    payload = json.dumps({"pane_id": "w1:p1", "status": "idle"})
    result = run(["event", "--payload", payload, "--json"], env)
    record = json.loads(result.stdout)
    assert record["status"] == "idle"
    assert record["nudge"] is True
    assert record["goal"] == 20
    assert record["reason"] == "ok"


def test_event_is_throttled_on_the_second_idle(env):
    run(["settings", f"nudge.quiet_hours={quiet_hours_that_exclude_now()}"], env)
    payload = json.dumps({"pane_id": "w1:p1", "status": "idle"})
    run(["event", "--payload", payload], env)
    second = run(["event", "--payload", payload, "--json"], env)
    record = json.loads(second.stdout)
    assert record["nudge"] is False
    assert "throttled" in record["reason"]


def test_event_ignores_non_idle_status(env):
    payload = json.dumps({"pane_id": "w1:p1", "status": "running"})
    record = json.loads(run(["event", "--payload", payload, "--json"], env).stdout)
    assert record["nudge"] is False
    assert "not idle" in record["reason"]


def test_event_respects_disabled_nudges(env, tmp_path):
    run(["settings", "nudge.enabled=false"], env)
    run(["settings", f"nudge.quiet_hours={quiet_hours_that_exclude_now()}"], env)
    payload = json.dumps({"status": "done"})
    result = run(["event", "--payload", payload, "--json"], env)
    record = json.loads(result.stdout)
    assert record["nudge"] is True, "the decision is computed, but sending is disabled"
    assert "disabled" in result.stderr


def test_event_force_bypasses_throttle(env):
    run(["settings", f"nudge.quiet_hours={quiet_hours_that_exclude_now()}"], env)
    payload = json.dumps({"status": "idle"})
    run(["event", "--payload", payload], env)
    forced = json.loads(run(["event", "--payload", payload, "--force", "--json"], env).stdout)
    assert forced["nudge"] is True


def test_startup_prepares_directories(env, tmp_path):
    result = run(["startup"], env)
    assert result.returncode == 0
    assert "word-practice v" in result.stdout
    assert (tmp_path / "state" / "books").is_dir()


def test_drill_without_a_tty_does_not_hang(env):
    result = run(["drill", "-n", "2"], env)
    assert result.returncode == 0
    assert "word practice" in result.stdout


def test_install_script_dry_run_is_harmless(tmp_path):
    env = dict(os.environ)
    env["HERDR_CONFIG"] = str(tmp_path / "config.toml")
    env["WORDS_BIN_DIR"] = str(tmp_path / "bin")
    env["PATH"] = f"{tmp_path / 'bin'}:" + env.get("PATH", "")
    result = subprocess.run(
        ["sh", str(ROOT / "scripts" / "install.sh"), "--dry-run"],
        cwd=str(ROOT), env=env, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    assert "dry-run" in result.stdout
    assert not (tmp_path / "config.toml").exists(), "dry-run must not write config"
    assert not (tmp_path / "bin" / "words").exists()


def test_setup_wires_keybindings_and_the_words_command(env, tmp_path):
    """`herdr plugin action invoke herdr-word-practice.setup` must be idempotent."""
    env["HERDR_CONFIG"] = str(tmp_path / "config.toml")
    env["WORDS_BIN_DIR"] = str(tmp_path / "bin")

    first = run(["setup", "--json"], env)
    assert first.returncode == 0, first.stderr
    payload = json.loads(first.stdout)
    text = (tmp_path / "config.toml").read_text()
    assert text.count("herdr-word-practice.drill") == 1
    assert "prefix+shift+w" in text and "prefix+alt+w" in text

    link = tmp_path / "bin" / "words"
    assert link.is_symlink()
    assert Path(os.path.realpath(link)).name == "words"

    second = json.loads(run(["setup", "--json"], env).stdout)
    assert (tmp_path / "config.toml").read_text() == text, "second run must not duplicate"
    assert any("已配置" in step for step in second["steps"])
    assert payload["dry_run"] is False
