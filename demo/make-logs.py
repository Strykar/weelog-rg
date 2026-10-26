#!/usr/bin/env python3
"""Generate a synthetic WeeChat logs tree for the demo recording."""
from __future__ import annotations

import gzip
import random
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

ME = "strykar"
NICKS = ["FlashCode", "nils_2", "tobias", "kestrel", "nadia", "oskar", "ferrum", "juno", "pell"]
TOPICS = {
    "#archlinux": [
        "pacman -Syu pulled in a new kernel, rebooting",
        "anyone else seeing systemd-resolved hang on boot?",
        "systemd 258 changed the unit ordering for network-online.target",
        "the wiki page on systemd-boot is the clearest explanation",
        "mkinitcpio warned about a missing firmware, harmless",
        "try `journalctl -b -1` to see the previous boot",
        "makepkg -si from the AUR snapshot fixed it",
        "pacman -Qdtq | pacman -Rns - cleans up orphans",
        "news item: https://archlinux.org/news/ before you upgrade",
        "systemd-analyze blame says NetworkManager-wait-online takes 6s",
    ],
    "#weechat": [
        "logger.file.time_format defaults to ISO 8601 now",
        "/set logger.file.color_lines on keeps the colours in logs",
        "the relay plugin works fine behind a reverse proxy",
        "/buffer merge is my favourite hidden feature",
        "script install go.py, then alt+j to jump",
        "weechat 4.7 shipped with a faster nicklist",
        "docs: https://weechat.org/files/doc/weechat/stable/",
        "rotated logs are compressed with zstd if you ask for it",
    ],
    "#python": [
        "asyncio.TaskGroup made my cleanup code so much simpler",
        "textual's Pilot API is great for testing TUIs",
        "uv run --script with PEP 723 metadata is the way",
        "ruff replaced flake8, isort and pyupgrade for me",
        "dataclasses with slots=True shaved some memory",
        "the new REPL in 3.13 has multiline editing",
        "pytest-asyncio auto mode saves a lot of decorators",
    ],
    "#tor": [
        "relay bandwidth looks healthy this week",
        "new consensus weight after the upgrade",
        "systemd unit for tor@default needs a restart after config change",
    ],
}
PM_LINES = [
    "hey, got a minute?",
    "sure, what's up",
    "that systemd fix you posted worked, thanks",
    "can you review my PR later?",
    "sent you the link: https://github.com/example/project/pull/42",
    "lunch tomorrow?",
    "the backup script finally runs from a timer",
]


def ts(d: date, sec: int) -> str:
    return (datetime(d.year, d.month, d.day) + timedelta(seconds=sec)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )


def chan_day(rng: random.Random, chan: str, d: date) -> str:
    out, sec = [], rng.randint(7, 10) * 3600
    regulars = rng.sample(NICKS, 5)
    for _ in range(rng.randint(12, 30)):
        sec += rng.randint(30, 1500)
        r = rng.random()
        if r < 0.08:
            n = rng.choice(NICKS)
            out.append(f"{ts(d, sec)}\t-->\t{n} (~{n}@user/{n}) has joined {chan}")
        elif r < 0.12:
            n = rng.choice(NICKS)
            out.append(f"{ts(d, sec)}\t<--\t{n} (~{n}@user/{n}) has quit (Ping timeout)")
        else:
            who = ME if rng.random() < 0.15 else rng.choice(regulars)
            out.append(f"{ts(d, sec)}\t{who}\t{rng.choice(TOPICS[chan])}")
    return "\n".join(out) + "\n"


def pm_day(rng: random.Random, peer: str, d: date) -> str:
    sec = rng.randint(12, 20) * 3600
    out = []
    for i in range(rng.randint(2, 6)):
        sec += rng.randint(20, 400)
        out.append(f"{ts(d, sec)}\t{peer if i % 2 == 0 else ME}\t{rng.choice(PM_LINES)}")
    return "\n".join(out) + "\n"


def main(root: Path) -> None:
    rng = random.Random(7)
    start, end = date(2026, 8, 1), date(2026, 10, 25)
    nets = {"libera": ["#archlinux", "#weechat", "#python"], "oftc": ["#tor"]}
    d = start
    while d <= end:
        for net, chans in nets.items():
            ndir = root / str(d.year) / net
            ndir.mkdir(parents=True, exist_ok=True)
            md = d.strftime("%m-%d")
            for chan in chans:
                if rng.random() < 0.85:
                    (ndir / f"{chan}.{md}.log").write_text(chan_day(rng, chan, d))
            if net == "libera":
                for peer in ("FlashCode", "tobias"):
                    if rng.random() < 0.3:
                        (ndir / f"{peer.lower()}.{md}.log").write_text(pm_day(rng, peer, d))
                if rng.random() < 0.2:
                    (ndir / f"nickserv.{md}.log").write_text(
                        f"{ts(d, 30000)}\tNickServ\tYou are now identified for {ME}.\n"
                    )
                (ndir / f"libera.{md}.log").write_text(
                    f"{ts(d, 29000)}\t--\tWelcome to the Libera.Chat Internet Relay Chat Network {ME}\n"
                )
        d += timedelta(days=1)

    old = [chan_day(rng, "#weechat", date(2025, 3, 1) + timedelta(days=i)) for i in range(120)]
    (root / "irc.freenode.#weechat.weechatlog").write_text("".join(old[60:]))
    with gzip.open(root / "irc.freenode.#weechat.weechatlog.1.gz", "wt") as f:
        f.write("".join(old[:60]))
    (root / "irc.libera.*status.weechatlog").write_text(
        f"{ts(start, 3600)}\t*status\tConnected to irc.libera.chat\n"
    )
    (root / "core.weechat.weechatlog").write_text(
        f"{ts(start, 100)}\t--\tPlugins loaded: irc, logger, relay, script\n"
    )


if __name__ == "__main__":
    main(Path(sys.argv[1]))
