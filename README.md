# weelog-rg

Search every kind of WeeChat log with ripgrep: channels, PMs, server buffers, services
(ChanServ, NickServ, ...), ZNC bouncer modules, and WeeChat's own monitor and core buffers,
in both the legacy flat layout (`plugin.name.weechatlog[.N][.gz]`) and the dated
`YYYY/network/buffer.MM-DD.log` hierarchy. Index years of history once, then search
gigabytes of it in well under a second on a modern NVMe SSD.

Three front ends share one stdlib-only core, `weelog_rg/`:

| | | |
| --- | --- | --- |
| **TUI** | `bin/weelog-rg` | Keyboard-driven: filter chips for network, channel, date and nick, colourised nicks, a live context pane, `$PAGER` jump on Enter, TSV export. [Install](#install) |
| **CLI** | `python -m weelog_rg` | Non-interactive, for scripts and pipelines: text, JSON lines or TSV, grep-style exit codes. [Command line](#command-line) |
| **WeeChat script** | `weechat/weelog.py` | `/weelog` searches from inside the client into a results buffer, with the logged time in the time column and WeeChat's own nick colours. [Inside WeeChat](#inside-weechat) |

Matching ignores case unless asked. Non-conversation buffers are classified and hidden
by default so you search what people said, not what servers announced.

## Demo

[demo/demo.cast](demo/demo.cast) is an [asciinema](https://asciinema.org) recording of
the TUI: search, filters, regex, archives, tree scoping, pager, export, theme.

```sh
asciinema play demo/demo.cast
```

## Install

**Recommended path (uses [`uv`](https://github.com/astral-sh/uv)):**

```sh
curl -L https://raw.githubusercontent.com/strykar/weelog-rg/main/bin/weelog-rg \
    -o ~/.local/bin/weelog-rg
chmod +x ~/.local/bin/weelog-rg
```

The shebang handles the Python environment. That's it.

**Manual venv** (if you can't use `uv`):

```sh
git clone https://github.com/strykar/weelog-rg
cd weelog-rg
python -m venv .venv && .venv/bin/pip install 'textual==8.2.3' 'rich==15.0.0'
.venv/bin/python bin/weelog-rg --logs ~/.local/share/weechat/logs
```

You'll also need [ripgrep](https://github.com/BurntSushi/ripgrep) on `$PATH`
(`pacman -S ripgrep`, `apt install ripgrep`, `brew install ripgrep`), and `zstd`
if any of your rotated logs are `.zst`. The PEP 723 shebang requires `uv >= 0.4`.

## Usage

```sh
weelog-rg --logs ~/.local/share/weechat/logs
weelog-rg --logs DIR --theme gruvbox
weelog-rg --help

# Or set the env var once and skip --logs:
export WEELOG_DIR=~/.local/share/weechat/logs
weelog-rg
```

`--logs` takes priority over `$WEELOG_DIR`. If neither is set, the tool
exits with a readable error and a hint. Older WeeChat setups keep logs under
`~/.weechat/logs` instead of the XDG path above.

Press `?` inside the app for every key. `Ctrl+Q` quits; `Ctrl+C` does not.

See **[docs/USER_GUIDE.md](docs/USER_GUIDE.md)** for the filter knobs, key bindings, and typical workflows.

## Files

Follows the XDG Base Directory spec:

| What          | Location                                        |
| ------------- | ----------------------------------------------- |
| Index cache   | `$XDG_CACHE_HOME/weelog-rg/index.json`   |
| Exports       | `/tmp/weelog-rg-<timestamp>-<random>.tsv` (on demand, with confirmation) |

No config file yet.

What the tool touches, since these are your private logs:

- **Reads** the logs directory, and `logger.conf` from your WeeChat config dir to learn the nick prefix and suffix you log with.
- **Writes** only the index cache above and, on `Ctrl+E` after you confirm, an export file in `/tmp` created with mode 0600. A write gate aborts anything else, including anything inside the logs directory.
- **Clipboard**: `y` and `Y` write to it through the terminal (OSC 52), only after you say yes once per session. It never reads the clipboard.
- **Runs** `rg`, `zstdcat` or `zcat` for compressed files, and your `$PAGER` on `Enter`.

## Command line

`python -m weelog_rg` is the same search without the TUI: one line per hit on
stdout, for scripts and pipelines. It needs the checkout on `PYTHONPATH` (or run it
from the checkout) and takes `--logs DIR` or `$WEELOG_DIR` like the TUI.

```sh
python -m weelog_rg --logs ~/.local/share/weechat/logs -u alice -s "kernel panic"
python -m weelog_rg -u alice -u bob --from 2026-01-01 --to 2026-03-01
python -m weelog_rg -s foo --format json | jq .message
python -m weelog_rg -s foo --format tsv | cut -f1,4,5
python -m weelog_rg -s "pacman" --context 2 --channel '#archlinux'
```

Matching ignores case unless `--case` is given. `--regex` switches the text to a
regular expression, `--events`, `--archives` and `--system` widen the search like the
TUI chips. Output stops at 500 hits with a note on stderr; `--limit N` changes that and
`--limit 0` means all. Exit status is 0 with hits, 1 without, 2 on error.
Colour follows `--color auto|always|never` and `NO_COLOR`.

## Inside WeeChat

`weechat/weelog.py` runs the same search inside the client. `/weelog [options] TEXT`
streams ripgrep hits into a `weelog` buffer, oldest first, with the logged time in
the time column and nicks in WeeChat's own colours. The logs directory and nick
prefix/suffix come from the live logger config, so there is nothing to configure.

```sh
git clone https://github.com/strykar/weelog-rg
ln -s "$PWD/weelog-rg/weechat/weelog.py" ~/.local/share/weechat/python/
```

Then `/python load weelog.py` in WeeChat, or symlink into `python/autoload/` instead.
The script imports the `weelog_rg` package from the checkout the symlink points at,
and `rg` must be on WeeChat's `PATH`.

Prefer one file with no checkout behind it? Build the self-contained version, which
is also what goes to weechat.org:

```sh
python3 scripts/build-weechat-script.py        # writes dist/weelog.py
cp dist/weelog.py ~/.local/share/weechat/python/
```

```
/weelog kernel panic
/weelog -nick alice -from 2026-01-01 kernel panic
/weelog -here -regex (merged|closed) PR #
/weelog -context 3 -nick alice kernel panic
/weelog -stop
/help weelog
```

The results buffer is marked `no_log`, so searches are never written back into the
logs. Typing into it runs `/weelog` again with what you typed.

## Roadmap

See [TODO.md](TODO.md) for what is still open (TUI shim over the package, weechat.org submission, jump to the live buffer).

## Contributing

PRs and issues welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for the development setup, testing guidelines, and style notes.

## License

MIT. See [LICENSE](LICENSE).
