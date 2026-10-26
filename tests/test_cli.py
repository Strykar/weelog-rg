from __future__ import annotations

import gzip
import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def run_cli(args, logs, tmp_path, env=None, use_logs_flag=True):
    full_env = {k: v for k, v in os.environ.items() if k not in ("NO_COLOR", "WEELOG_DIR")}
    # The write gate refuses a cache inside the logs dir, and synthetic_logs is tmp_path.
    full_env["XDG_CACHE_HOME"] = str(tmp_path.parent / f"{tmp_path.name}-cache")
    full_env["PYTHONPATH"] = str(REPO_ROOT)
    if env:
        full_env.update(env)
    argv = [sys.executable, "-m", "weelog_rg"]
    if use_logs_flag:
        argv += ["--logs", str(logs)]
    return subprocess.run(argv + list(args), capture_output=True, text=True, env=full_env,
                          cwd=str(tmp_path))


def test_text_output_is_chronological_and_exit_0(synthetic_logs, tmp_path):
    r = run_cli(["--search", "morning"], synthetic_logs, tmp_path)
    assert r.returncode == 0, r.stderr
    lines = r.stdout.splitlines()
    assert lines == [
        "2026-01-02 10:00:30  example-network/#channel-one  <alice> good morning",
        "2026-01-02 10:01:00  example-network/#channel-one  <bob> morning - https://example.org/path?q=1",
    ]
    assert "\x1b[" not in r.stdout  # not a TTY, so no colour


def test_no_hits_exit_1_and_silent(synthetic_logs, tmp_path):
    r = run_cli(["--search", "nothing matches this"], synthetic_logs, tmp_path)
    assert r.returncode == 1
    assert r.stdout == "" and r.stderr == ""


def test_nick_alone_drives_the_search(synthetic_logs, tmp_path):
    r = run_cli(["-u", "alice"], synthetic_logs, tmp_path)
    assert r.returncode == 0
    msgs = [ln.split("> ", 1)[1] for ln in r.stdout.splitlines()]
    assert msgs == ["good morning", "private hello", "day two message"]


def test_case_insensitive_by_default(synthetic_logs, tmp_path):
    assert run_cli(["-s", "GOOD Morning"], synthetic_logs, tmp_path).returncode == 0
    assert run_cli(["-s", "GOOD Morning", "--case"], synthetic_logs, tmp_path).returncode == 1
    assert run_cli(["-u", "ALICE", "-s", "MORNING"], synthetic_logs, tmp_path).returncode == 0


def test_search_text_may_start_with_a_dash(synthetic_logs, tmp_path):
    r = run_cli(["--search=- https"], synthetic_logs, tmp_path)
    assert r.returncode == 0 and "<bob>" in r.stdout
    # Looks like an rg option; must reach rg as a pattern, never as a flag.
    r = run_cli(["--search=--files"], synthetic_logs, tmp_path)
    assert r.returncode == 1 and r.stdout == "" and r.stderr == ""


def test_default_limit_truncates_with_a_note(tmp_path):
    dated = tmp_path / "logs" / "2026" / "net"
    dated.mkdir(parents=True)
    (dated / "#c.01-02.log").write_text(
        "".join(f"2026-01-02 10:{i // 60:02d}:{i % 60:02d}\talice\tline {i}\n" for i in range(600)),
        encoding="utf-8")
    r = run_cli(["-s", "line"], tmp_path / "logs", tmp_path)
    assert r.returncode == 0 and r.stdout.count("\n") == 500
    assert "--limit 0" in r.stderr
    r = run_cli(["-s", "line", "--limit", "0"], tmp_path / "logs", tmp_path)
    assert r.stdout.count("\n") == 600 and r.stderr == ""


def test_regex_flag(synthetic_logs, tmp_path):
    # Patterns see the whole log line, so anchor on the tab before the message.
    r = run_cli(["-s", r"\tday (two|three) message$", "--regex"], synthetic_logs, tmp_path)
    assert r.returncode == 0 and r.stdout.count("\n") == 1
    r = run_cli(["-s", "day (two|three) message"], synthetic_logs, tmp_path)
    assert r.returncode == 1  # fixed string by default


def test_json_lines(synthetic_logs, tmp_path):
    r = run_cli(["-s", "morning", "--format", "json"], synthetic_logs, tmp_path)
    assert r.returncode == 0
    recs = [json.loads(ln) for ln in r.stdout.splitlines()]
    assert [x["nick"] for x in recs] == ["alice", "bob"]
    first = recs[0]
    assert first["timestamp"] == "2026-01-02 10:00:30"
    assert first["network"] == "example-network" and first["buffer"] == "#channel-one"
    assert first["message"] == "good morning" and first["event"] is False
    assert first["line"] == 3 and first["path"].endswith("#channel-one.01-02.log")
    assert "context" not in first


def test_tsv_columns_and_embedded_tabs(tmp_path):
    logs = tmp_path / "logs"
    (logs / "2026" / "net").mkdir(parents=True)
    (logs / "2026" / "net" / "#c.01-02.log").write_text(
        "2026-01-02 10:00:00\talice\tcol1\tcol2 inside message\n", encoding="utf-8")
    r = run_cli(["-s", "col1", "--format", "tsv"], logs, tmp_path)
    assert r.returncode == 0
    cols = r.stdout.rstrip("\n").split("\t")
    assert cols[:5] == ["2026-01-02 10:00:00", "net", "#c", "alice", "col1 col2 inside message"]
    assert cols[5].endswith("#c.01-02.log") and cols[6] == "1" and cols[7] == "0"
    assert len(cols) == 8


def test_context_text(synthetic_logs, tmp_path):
    r = run_cli(["-s", "good morning", "--context", "1"], synthetic_logs, tmp_path)
    assert r.returncode == 0
    out = r.stdout.splitlines()
    # Events hidden: the join and topic above alice are skipped, bob below shows.
    assert out[0].startswith("2026-01-02 10:00:30  example-network/#channel-one  <alice> good morning")
    assert any(ln.startswith(">> 10:00:30") and "good morning" in ln for ln in out)
    assert any(ln.startswith("   10:01:00") and "<bob>" in ln for ln in out)


def test_context_json_and_events(synthetic_logs, tmp_path):
    r = run_cli(["-s", "good morning", "--context", "1", "--events", "--format", "json"],
                synthetic_logs, tmp_path)
    assert r.returncode == 0
    rec = json.loads(r.stdout.splitlines()[0])
    ctx = rec["context"]
    assert [c["line"] for c in ctx] == [2, 3, 4]
    assert ctx[0]["event"] is True and ctx[0]["nick"] == "--"
    assert ctx[1]["hit"] is True and ctx[2]["hit"] is False


def test_context_rejected_for_tsv(synthetic_logs, tmp_path):
    r = run_cli(["-s", "morning", "--context", "1", "--format", "tsv"], synthetic_logs, tmp_path)
    assert r.returncode == 2 and "context" in r.stderr


def test_date_window(synthetic_logs, tmp_path):
    r = run_cli(["-u", "alice", "--from", "2026-01-03"], synthetic_logs, tmp_path)
    assert r.stdout.splitlines() and all("2026-01-03" in ln for ln in r.stdout.splitlines())
    r = run_cli(["-u", "alice", "--to", "2026-01-02"], synthetic_logs, tmp_path)
    assert r.stdout.splitlines() and all("2026-01-02" in ln for ln in r.stdout.splitlines())
    r = run_cli(["-u", "alice", "--from", "yesterday"], synthetic_logs, tmp_path)
    assert r.returncode == 2 and "YYYY-MM-DD" in r.stderr


def test_network_and_channel_scope(synthetic_logs, tmp_path):
    r = run_cli(["-u", "alice", "--channel", "#CHANNEL-ONE"], synthetic_logs, tmp_path)
    assert r.returncode == 0
    assert all("#channel-one" in ln and "private" not in ln for ln in r.stdout.splitlines())
    r = run_cli(["-s", "legacy", "--network", "legacy-network"], synthetic_logs, tmp_path)
    assert r.returncode == 0 and "dave" in r.stdout
    r = run_cli(["-s", "legacy", "--network", "example-network"], synthetic_logs, tmp_path)
    assert r.returncode == 1
    r = run_cli(["-s", "x", "--channel", "#nope"], synthetic_logs, tmp_path)
    assert r.returncode == 2 and "#nope" in r.stderr


def test_archives_and_system(synthetic_logs, tmp_path):
    assert run_cli(["-s", "archived gzip"], synthetic_logs, tmp_path).returncode == 1
    r = run_cli(["-s", "archived gzip", "--archives"], synthetic_logs, tmp_path)
    assert r.returncode == 0 and "frank" in r.stdout
    assert run_cli(["-s", "ZNC status"], synthetic_logs, tmp_path).returncode == 1
    assert run_cli(["-s", "ZNC status", "--system"], synthetic_logs, tmp_path).returncode == 0


def test_limit(synthetic_logs, tmp_path):
    r = run_cli(["-u", "alice", "--limit", "1"], synthetic_logs, tmp_path)
    assert r.returncode == 0 and r.stdout.count("\n") == 1


def test_color_flag_and_no_color_env(synthetic_logs, tmp_path):
    r = run_cli(["-s", "morning", "--color", "always"], synthetic_logs, tmp_path)
    assert "\x1b[38;5;" in r.stdout and r.stdout.count("\x1b[0m") >= 2
    r = run_cli(["-s", "morning", "--color", "always"], synthetic_logs, tmp_path, env={"NO_COLOR": "1"})
    assert "\x1b[" in r.stdout  # explicit always wins
    r = run_cli(["-s", "morning", "--color", "auto"], synthetic_logs, tmp_path, env={"NO_COLOR": "1"})
    assert "\x1b[" not in r.stdout


def test_logs_dir_from_env_and_missing(synthetic_logs, tmp_path):
    r = run_cli(["-s", "morning"], synthetic_logs, tmp_path,
                env={"WEELOG_DIR": str(synthetic_logs)}, use_logs_flag=False)
    assert r.returncode == 0
    r = run_cli(["-s", "morning"], synthetic_logs, tmp_path, use_logs_flag=False)
    assert r.returncode == 2 and "WEELOG_DIR" in r.stderr
    r = run_cli(["-s", "morning"], tmp_path / "missing", tmp_path)
    assert r.returncode == 2 and "does not exist" in r.stderr


def test_nothing_to_search_is_a_usage_error(synthetic_logs, tmp_path):
    r = run_cli([], synthetic_logs, tmp_path)
    assert r.returncode == 2 and "--search" in r.stderr and "--user" in r.stderr


def test_non_utf8_filename_is_printable_in_every_format(tmp_path):
    logs = tmp_path / "logs"
    logs.mkdir()
    raw = os.fsdecode(b"irc.net.\xff\xfechan.weechatlog")
    (logs / raw).write_text("2026-01-02 10:00:00\talice\thello there\n", encoding="utf-8")
    for fmt in ("text", "json", "tsv"):
        r = run_cli(["-s", "hello", "--format", fmt], logs, tmp_path)
        assert r.returncode == 0, (fmt, r.stderr)
        assert "hello there" in r.stdout
    rec = json.loads(run_cli(["-s", "hello", "--format", "json"], logs, tmp_path).stdout)
    assert "�" in rec["path"]


def test_control_bytes_in_log_content_do_not_reach_stdout(tmp_path):
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "irc.net.#c.weechatlog").write_text(
        "2026-01-02 10:00:00\t\x1932al\x1b]0;x\x07ice\x1c\thi \x1b[31mred\x1b[0m \x1934bold\n",
        encoding="utf-8")
    r = run_cli(["-s", "hi", "--format", "json"], logs, tmp_path)
    assert r.returncode == 0
    rec = json.loads(r.stdout)
    assert rec["nick"] == "al]0;xice"
    assert rec["message"] == "hi [31mred[0m bold"
    assert not any(ord(c) < 0x20 or 0x7f <= ord(c) <= 0x9f for c in r.stdout.replace("\n", ""))


def test_broken_pipe_is_quiet(synthetic_logs, tmp_path):
    env = {k: v for k, v in os.environ.items() if k not in ("NO_COLOR", "WEELOG_DIR")}
    env["XDG_CACHE_HOME"] = str(tmp_path.parent / f"{tmp_path.name}-cache")
    env["PYTHONPATH"] = str(REPO_ROOT)
    # head -c 0 closes at once; the writer must then die on EPIPE like grep, no traceback.
    dated = tmp_path / "logs" / "2026" / "net"
    dated.mkdir(parents=True)
    (dated / "#c.01-02.log").write_text(
        "".join(f"2026-01-02 10:00:{i % 60:02d}\talice\tline {i} " + "x" * 200 + "\n"
                for i in range(5000)), encoding="utf-8")
    cmd = (f"{sys.executable} -m weelog_rg --logs {tmp_path / 'logs'} -s line | head -c 0; "
           "echo rc=${PIPESTATUS[0]}")
    r = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, env=env, cwd=str(tmp_path))
    assert "Traceback" not in r.stderr and "BrokenPipe" not in r.stderr
    assert r.stdout.strip() in ("rc=0", "rc=141")


def test_context_through_a_gz_archive(tmp_path):
    logs = tmp_path / "logs"
    logs.mkdir()
    with gzip.open(logs / "irc.net.#c.weechatlog.1.gz", "wt", encoding="utf-8") as f:
        f.write("2024-01-15 08:00:00\tfrank\tbefore\n2024-01-15 08:00:01\tfrank\tarchived hit\n"
                "2024-01-15 08:00:02\tfrank\tafter\n")
    r = run_cli(["-s", "archived hit", "--archives", "--context", "1"], logs, tmp_path)
    assert r.returncode == 0
    assert "before" in r.stdout and "after" in r.stdout
