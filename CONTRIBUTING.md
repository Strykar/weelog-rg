# Contributing

Thanks for taking an interest. The TUI is a single-file script, the core it shares with the WeeChat script lives in `weelog_rg/`. Don't be shy.

## Quick checklist

Before opening a PR:

- [ ] `ruff check bin/weelog-rg weelog_rg weechat tests` is clean
- [ ] `pytest` is green (this includes `tests/test_build.py`, which rebuilds the
      self-contained WeeChat script and loads it without the package on the path)
- [ ] If you touched the TUI, run `pytest tests/test_fuzz.py` with two or three different `--seed` values

## Development setup

You'll need Python ≥ 3.12, `ripgrep`, and either `uv` or a venv with `textual>=0.80 rich>=13 pytest`. Install `zstd` too if you want full `.zst` decompression test coverage (tests skip gracefully without it).

```sh
git clone <repo>
cd weelog-rg
python -m venv .venv
.venv/bin/pip install textual 'rich>=13' pytest ruff
.venv/bin/pytest
```

Or with `uv`, which installs the pinned test tools from `uv.lock` on first use:

```sh
uv run pytest
uv run ruff check bin/weelog-rg weelog_rg weechat tests
```

## A few things to know

The TUI is one executable script under `bin/`; `weelog_rg/` holds the index, query, parser and ripgrep runner, and `weechat/weelog.py` is the in-client script built on them. Three things worth flagging up front:

1. **The PEP 723 shebang is load-bearing.** `#!/usr/bin/env -S uv run --script --quiet` is what makes the script a drop-in, so users don't need to create a venv. The `--script` flag matters; without it `uv` recursively re-invokes itself.
2. **The logs directory is read-only.** Every filesystem write goes through `assert_writable(path)`. The allowlist covers the XDG cache and `/tmp/weelog-rg-*.tsv` exports. If you find yourself reaching for `open("w")` or `write_text` directly, please route it through the gate. The test suite (`tests/test_readonly.py`) checks this, but a heads-up first saves a review round trip.
3. **`ripgrep` is the search engine.** This approach searches multi-gigabyte log directories in well under a second on a modern NVMe SSD, more than most humans accumulate in a lifetime. A persistent index would add maintenance and staleness without buying us anything noticeable, so let's not go there.

Two more things about the WeeChat script:

- `weechat/weelog.py` is the source and imports the package. `python3
  scripts/build-weechat-script.py` inlines the package into `dist/weelog.py`, the
  one-file form weechat.org requires. Run `uvx weechat-script-lint dist/weelog.py`
  on that file before a submission; the score must be 100.
- `scripts/weechat-e2e/run.sh WORKDIR LOGS 'CMD;;CMD'` drives either script inside
  `weechat-headless` with a throwaway home (logging off, cache in WORKDIR), runs the
  `/weelog` commands and dumps the results buffer to `WORKDIR/out.txt`. It is how the
  unhook-inside-callback crash was found; use it for anything that touches hooks.

The rest of the split is tracked in `TODO.md` item 2. Until `bin/weelog-rg` becomes a shim, shared logic exists in both places: change it in `weelog_rg/` and in the script, and extend the parity tests in `tests/test_package.py` if you touch `parse_line` or `classify_buffer`.

## Design notes

The code comments are deliberately short. The *why* lives here.

### Buffer kinds

`classify_buffer(network, buffer)` returns one tag:

- **channel**: names starting with `#`, `&`, `+`, `!`
- **pm**: plain nicks
- **server**: the IRC server's own connection messages (MOTD, notices)
- **znc**: your ZNC bouncer's `*status`, `*controlpanel`, etc. Both prefix and suffix asterisks count, since ZNC lets you pick.
- **service**: bots like ChanServ and NickServ
- **monitor**: WeeChat's `chanmon`, `highmon`, `newsmon` aggregators
- **user_core**: `core.weechat` (config changes, plugin loads)
- **soju**: stub. We need real soju logs to write a detector.
- **other**: anything else under the synthetic `(core)` network

`channel`, `pm`, and `server` are always on. The rest are off and gated by a checkbox in the filter card. Picking a node in the tree narrows scope but never bypasses that checkbox; without it ticked, those buffers stay out of the search.

### Write gate

`assert_writable(path)` is the only place we write to disk. It permits two locations and nothing else:

1. The XDG cache directory (for the index JSON)
2. `/tmp/weelog-rg-*.tsv` (for exports, after the user confirms)

Any path that resolves outside both, or inside `--logs` (even if the user pointed `--logs` at `/tmp`), raises `WriteRefused`. At startup that exits with the message; in the export dialog it becomes a notification and the session continues. `test_write_gate.py` covers the refusal branches. `test_readonly.py` checksums the logs tree before and after a real session and fails if a single byte moved.

### Why ripgrep, not an index

We hand `rg` a list of paths per query. No persistent index means no staleness to chase, and `rg -z` reads compressed logs (gzip and zstd, the two compression types WeeChat's logger supports) transparently. The preview pane reads `.gz` via Python's `gzip` module and `.zst` via the system `zstdcat` (no Python zstd dependency). The whole approach searches multi-gigabyte log directories in well under a second on a modern NVMe SSD, which is more history than most humans collect in a lifetime. There's nothing for an index layer to improve here.

### Why the search debounces and renders once

Two things would make the TUI feel laggy if we let them.

First, firing a search on every keystroke. Backspacing through a query widens the result set every step. The fix is a 300 ms debounce on input changes.

Second, streaming rows into the table while rg runs. A cancelled search then has to clear a bunch of rows it just rendered. The fix is to collect quietly during rg and render once at the end. The search worker is `@work(exclusive=True)` so a fresh keystroke cancels the prior `rg` cleanly. Cancelled searches now cost zero render work.

### Handling user-configurable logger options

WeeChat's logger has a few options users tweak that change what's actually written to log files. We accommodate them so the parser doesn't break on non-default configurations:

- **Timestamp format** (`logger.file.time_format`). Default on fresh installs is `%@%F %T.%fZ` (ISO 8601 with microseconds and a trailing Z); many users override to the older `%Y-%m-%d %H:%M:%S`. `parse_timestamp` accepts both.
- **Nick wrappers** (`logger.file.nick_prefix` / `nick_suffix`). When set, the file writes the nick column as `<alice>` or `|alice|` or whatever the user picked. We read those values from `logger.conf` at startup, wrap them around the search regex so `alice` still matches, and strip them from the parsed `who` for display.
- **Colour codes in lines** (`logger.file.color_lines`). When on, log lines contain WeeChat colour escape bytes. `strip_weechat_colors` removes them from the message body so the rendering stays readable.
- **Info lines** (`logger.file.info_lines`). When on, WeeChat writes log-start and log-end markers into the file. They land in the search results as event-prefixed rows and stay visible only when `events` is on.

### Date filtering on legacy logs

Dated logs are one file per day, so we can gate them at the path level. Legacy single-file logs span all dates, so the path gate can't help. The search loop post-filters those by the matched line's own timestamp.

### Nick matching

Subsequence, fzf-style. Every character of your input must appear in order in the target nick. The regex is anchored between tabs so the match stays strictly in the nick column. Body mentions don't leak. Multiple nicks (space or comma separated) form an OR.

### PM direction arrow

Private buffers are named after the remote nick. When the *local* user is the speaker, the buffer name and the speaker name are different people, which reads ambiguously. The buffer column adds an arrow that always points at the speaker:

- `← <nick>`: remote is speaking
- `→ <nick>`: local user is speaking

### Index cache

Lives at `$XDG_CACHE_HOME/weelog-rg/index.json`. The key is a SHA-256 of the logs directory path plus the name + mtime + size of every top-level entry, plus the name + mtime of each network subdirectory under the year folders. On the common Linux filesystems (ext4, xfs, btrfs) this means almost any change inside the logs tree invalidates the cache, since adding a file bumps its parent directory's mtime. Treat the cache as pure derived state; any read failure rebuilds from disk.

### Responsive sizing

`on_resize` applies a class to the Screen (`-narrow` under 100 columns, `-wide` at 180 or more). CSS rules scoped to those classes contract or widen the tree and context panes. On first launch under 70 cols the tree auto-hides and the context pane defaults off so the results aren't crowded. `F2` / `F3` / `F4` toggle the filter card, context pane, and tree at any time.

## Testing

Three layers, roughly:

- **Unit tests** cover pure helpers (`parse_line`, classifier). No mocks, no I/O.
- **Integration tests** use small synthetic log trees under `tests/conftest.py`, exercised through `build_index`, `select_files`, and `run_search`. They shell out to real `rg`.
- **Fuzz** (`tests/test_fuzz.py`) drives the Textual app via `Pilot` with random knob permutations and asserts invariants after each one. Several real bugs surfaced this way during development. If you add a new knob, please extend the invariant list so the next regression doesn't slip through.
