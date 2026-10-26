# weelog-rg

Fast, keyboard-driven TUI for reading and searching every kind of WeeChat log: channels, PMs, server buffers, services (ChanServ, NickServ, ...), ZNC bouncer modules, and WeeChat's own monitor and core buffers. Both the legacy flat layout (`plugin.name.weechatlog[.N][.gz]`) and the dated `YYYY/network/buffer.MM-DD.log` hierarchy.

Index years of history once, then search gigabytes of it in well under a second on a modern NVMe SSD. Filter by network, channel, date range, or nick. Every hit gets colourised nicks, a live context preview, and a `$PAGER` jump on Enter. Non-conversation buffers are classified and rendered so you can read them as themselves rather than as fake chat.

> *(demo asciinema link to be added)*

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

## Roadmap

See [TODO.md](TODO.md) for upcoming work (non-interactive CLI mode, reusable-package refactor).

## Contributing

PRs and issues welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for the development setup, testing guidelines, and style notes.

## License

MIT. See [LICENSE](LICENSE).
