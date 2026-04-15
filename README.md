# weelog-hindsight

Fast, keyboard-driven TUI for reading and searching every kind of WeeChat log: channels, PMs, server buffers, services (ChanServ, NickServ, ...), ZNC bouncer modules, and WeeChat's own monitor and core buffers. Both the legacy flat layout (`plugin.name.weechatlog[.N][.gz]`) and the dated `YYYY/network/buffer.MM-DD.log` hierarchy.

Index years of history once, then search gigabytes of it in well under a second on a modern NVMe SSD. Filter by network, channel, date range, or nick. Every hit gets colourised nicks, a live context preview, and a `$PAGER` jump on Enter. Non-conversation buffers are classified and rendered so you can read them as themselves rather than as fake chat.

> *(demo asciinema link to be added)*

## Install

**Recommended path (uses [`uv`](https://github.com/astral-sh/uv)):**

```sh
curl -L https://raw.githubusercontent.com/strykar/weelog-hindsight/main/bin/weelog-hindsight \
    -o ~/.local/bin/weelog-hindsight
chmod +x ~/.local/bin/weelog-hindsight
```

The shebang handles the Python environment. That's it.

**Manual venv** (if you can't use `uv`):

```sh
git clone https://github.com/strykar/weelog-hindsight
cd weelog-hindsight
python -m venv .venv && .venv/bin/pip install 'textual>=0.80' 'rich>=13'
.venv/bin/python bin/weelog-hindsight --logs ~/.local/share/weechat/logs
```

You'll also need [ripgrep](https://github.com/BurntSushi/ripgrep) on `$PATH`
(`pacman -S ripgrep`, `apt install ripgrep`, `brew install ripgrep`).
The PEP 723 shebang requires `uv >= 0.4`.

## Usage

```sh
weelog-hindsight --logs ~/.local/share/weechat/logs
weelog-hindsight --logs DIR --theme gruvbox
weelog-hindsight --help

# Or set the env var once and skip --logs:
export WEELOG_DIR=~/.local/share/weechat/logs
weelog-hindsight
```

`--logs` takes priority over `$WEELOG_DIR`. If neither is set, the tool
exits with a readable error and a hint.

See **[docs/USER_GUIDE.md](docs/USER_GUIDE.md)** for the filter knobs, key bindings, and typical workflows.

## Files

Follows the XDG Base Directory spec:

| What          | Location                                        |
| ------------- | ----------------------------------------------- |
| Index cache   | `$XDG_CACHE_HOME/weelog-hindsight/index.json`   |
| Exports       | `/tmp/weelog-hindsight-<timestamp>.tsv` (on demand, with confirmation) |

No config file yet.

The script is gated such that it can never alter or write to the user-supplied `--logs` directory, only XDG cache.

## Roadmap

See [TODO.md](TODO.md) for upcoming work (non-interactive CLI mode, reusable-package refactor).

## Contributing

PRs and issues welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for the development setup, testing guidelines, and style notes.

## License

MIT. See [LICENSE](LICENSE).
