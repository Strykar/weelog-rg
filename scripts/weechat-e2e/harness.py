import os
import re
import weechat

weechat.register("harness", "x", "0.1", "MIT", "e2e harness for weelog", "", "")
OUT = os.environ["HARNESS_OUT"]
CMDS = [c for c in os.environ["HARNESS_CMDS"].split(";;") if c]
DONE_RE = re.compile(r"\d+ hits? in \d")
state = {"i": 0, "waiting": False, "ticks": 0}
open(OUT, "w", encoding="utf-8").close()


def out(text):
    with open(OUT, "a", encoding="utf-8") as fh:
        fh.write(text)


def buffer_lines(buf):
    h_buf = weechat.hdata_get("buffer")
    h_lines = weechat.hdata_get("lines")
    h_line = weechat.hdata_get("line")
    h_data = weechat.hdata_get("line_data")
    own = weechat.hdata_pointer(h_buf, buf, "own_lines")
    line = weechat.hdata_pointer(h_lines, own, "first_line")
    out = []
    while line:
        d = weechat.hdata_pointer(h_line, line, "data")
        date = weechat.hdata_time(h_data, d, "date")
        prefix = weechat.string_remove_color(weechat.hdata_string(h_data, d, "prefix"), "")
        msg = weechat.string_remove_color(weechat.hdata_string(h_data, d, "message"), "")
        out.append((date, prefix, msg))
        line = weechat.hdata_move(h_line, line, 1)
    return out


def dump_results(cmd):
    buf = weechat.buffer_search("python", "weelog")
    out(f"### {cmd}\n")
    if not buf:
        out("NO weelog BUFFER\n")
        return
    out("title: " + weechat.string_remove_color(weechat.buffer_get_string(buf, "title"), "") + "\n")
    for date, prefix, msg in buffer_lines(buf):
        out(f"{date}\t{prefix}\t{msg}\n")


def finish():
    out("### core buffer lines mentioning weelog or python\n")
    for _date, prefix, msg in buffer_lines(weechat.buffer_search_main()):
        if "weelog" in msg or "python" in msg.lower() or "python" in prefix.lower():
            out(f"{prefix}\t{msg}\n")
    weechat.command("", "/quit")


def tick(data, remaining):
    state["ticks"] += 1
    if state["ticks"] > 240:  # 120 s
        out("TIMEOUT\n")
        finish()
        return weechat.WEECHAT_RC_OK
    if state["waiting"]:
        buf = weechat.buffer_search("python", "weelog")
        title = weechat.buffer_get_string(buf, "title") if buf else ""
        if DONE_RE.search(title):
            dump_results(CMDS[state["i"]])
            state["waiting"] = False
            state["i"] += 1
        return weechat.WEECHAT_RC_OK
    if state["i"] >= len(CMDS):
        finish()
        return weechat.WEECHAT_RC_OK
    cmd = CMDS[state["i"]]
    if cmd.startswith("!"):  # fire and forget (error paths), no results to wait for
        weechat.command("", cmd[1:])
        state["i"] += 1
        return weechat.WEECHAT_RC_OK
    weechat.command("", cmd)
    state["waiting"] = True
    return weechat.WEECHAT_RC_OK


weechat.hook_timer(500, 0, 0, "tick", "")
