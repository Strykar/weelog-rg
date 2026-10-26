# TODO

High-level roadmap. Issues / PRs welcome.

## Performance

- [ ] `_render_rows` rebuilds the whole DataTable on every compact toggle.
  Fine at 500 rows, painful if the cap goes up.
- [ ] `select_files` re-filters per-file each call. Pre-partition by network
  in `build_index` if scope filters become a hot path.

## Known limitations

- The 500-match cap returns the first 500 hits in rg's stream order (roughly
  newest-year-first for dated layouts), not chronologically. The title shows
  "500+ (truncated)" but doesn't explain the ordering.
- Rotated log siblings (`.weechatlog.1.gz`, `.2.gz`) can overlap with the
  live file near the rotation boundary, producing duplicate hits when
  `archives` is on. Worth a note in the user guide.


## 1. Non-interactive CLI mode

Add a CLI surface for scripting, pipelines, and quick one-liners. No TUI, no Textual, plain text output to stdout.

Status: done as `python -m weelog_rg` (`weelog_rg/cli.py`, tests in
`tests/test_cli.py`). Differences from the sketch below: the archive flag is
`--archives` (rotated logs are `.gz` or `.zst`), the 500-hit default cap
matches the TUI and the WeeChat script (`--limit 0` for all, truncation is
noted on stderr), and hits are printed oldest first. Wiring it into
the `weelog-rg` executable waits for the shim in item 2.

```
weelog-rg --logs DIR --user alice --user bob --search "topic word"
weelog-rg --logs DIR --user alice --from 2026-01-01 --to 2026-03-01
weelog-rg --logs DIR --search foo --format json
```

Shape:

- `--user/-u` repeatable; builds the same `\t<nick>\t` anchor as the TUI.
- `--search/-s` optional body pattern (fixed-string by default; `--regex` to switch). If absent, nick-alone drives the output.
- `--network`, `--channel`, `--from`, `--to`, `--include-gz` mirror the TUI knobs.
- `--context N` for `grep --context=N` style surrounding lines, default 0.
- `--format text|json|tsv`, default text. `text` preserves nick colour when stdout is a TTY, strips it on a pipe (respect `NO_COLOR`).
- Exit 0 if matches, 1 if none (grep convention).

Reuse `Query`, `select_files`, and `run_search` without modification, since the TUI is already a thin layer over those. The CLI should live in a single module (`cli.py`) and share the existing index cache.

## 2. Refactor into a reusable package

Lift the logic out of the single-file script so a future WeeChat plugin (in-process, hooking `logger_backlog_*` or reading the on-disk files) can import and share it.

Status: `weelog_rg/{index,query,parse,search}.py` exist and are stdlib-only
(`tests/test_package.py` enforces it). `weechat/weelog.py` imports them.
`bin/weelog-rg` still carries its own copy of the core; the parity tests pin
`parse_line` and `classify_buffer`. Open:

- Turn `bin/weelog-rg` into the shim. Blocked on how the PEP 723 drop-in
  gets the package: a git dependency in the script header once the repo is
  public, or a PyPI release.
- `render.py` / `terminal.py` and the `tui/` move.
- weechat.org accepts one file per script; `scripts/build-weechat-script.py`
  inlines the package into `dist/weelog.py` for that.

## 3. WeeChat script follow-ups

- Jump from a hit to the live buffer and show context (cursor mode or a
  `/weelog -go N` subcommand).
- weechat.org submission: build `dist/weelog.py`, run `weechat-script-lint`
  on it (must score 100), fill the "Add script" pull request template, one
  commit adding `python/weelog.py`, subject `New script weelog.py: ...`. The
  description has to say how this differs from `grep.py`.

Suggested package layout:

```
weelog_rg/
├── __init__.py          # exports public API surface
├── index.py             # LogFile, build_index, cache, mask parsing
├── query.py             # Query dataclass, date/nick/scope helpers
├── search.py            # ripgrep runner + async iterator of Match
├── parse.py             # parse_line, event detection
├── render.py            # nick_color, render_message, format_relative
├── terminal.py          # terminal_autolinks_urls, OSC 52, OSC 8 helpers
├── tui/
│   ├── app.py           # WeelogRg(App) + ConfirmExport(ModalScreen)
│   └── ...
└── cli.py               # non-interactive surface from item 1
```

Constraints:

- Core modules (`index`, `query`, `search`, `parse`) **must not import textual or rich**. Keeping them free of UI deps is what lets a WeeChat plugin running inside the weechat process reuse them.
- `render.py` may optionally return Rich renderables but should also expose plain-string equivalents.
- The script `bin/weelog-rg` becomes a thin shim that imports `weelog_rg.tui.app:main`.
- Keep the PEP 723 shebang story working for drop-in users.

A WeeChat Python plugin would then be ~50 lines importing `index` + `search` to serve queries from inside the running client, reusing the exact same parser and mask handling as the external TUI.

## Nice-to-haves

- `--theme` persisted between runs (config file in `$XDG_CONFIG_HOME`).
- IRC colour code stripping in preview (weechat may write `\x03NN` codes depending on `color_lines`).
- Buffer counts in the tree reflect current-query matches (`3/173`) in addition to the file count.
