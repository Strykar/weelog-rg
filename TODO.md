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

```
weelog-hindsight --logs DIR --user alice --user bob --search "topic word"
weelog-hindsight --logs DIR --user alice --from 2026-01-01 --to 2026-03-01
weelog-hindsight --logs DIR --search foo --format json
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

Suggested package layout:

```
weelog_hindsight/
├── __init__.py          # exports public API surface
├── index.py             # LogFile, build_index, cache, mask parsing
├── query.py             # Query dataclass, date/nick/scope helpers
├── search.py            # ripgrep runner + async iterator of Match
├── parse.py             # parse_line, event detection
├── render.py            # nick_color, render_message, format_relative
├── terminal.py          # terminal_autolinks_urls, OSC 52, OSC 8 helpers
├── tui/
│   ├── app.py           # Hindsight(App) + ConfirmExport(ModalScreen)
│   └── ...
└── cli.py               # non-interactive surface from item 1
```

Constraints:

- Core modules (`index`, `query`, `search`, `parse`) **must not import textual or rich**. Keeping them free of UI deps is what lets a WeeChat plugin running inside the weechat process reuse them.
- `render.py` may optionally return Rich renderables but should also expose plain-string equivalents.
- The script `bin/weelog-hindsight` becomes a thin shim that imports `weelog_hindsight.tui.app:main`.
- Keep the PEP 723 shebang story working for drop-in users.

A WeeChat Python plugin would then be ~50 lines importing `index` + `search` to serve queries from inside the running client, reusing the exact same parser and mask handling as the external TUI.

## Nice-to-haves

- `--theme` persisted between runs (config file in `$XDG_CONFIG_HOME`).
- IRC colour code stripping in preview (weechat may write `\x03NN` codes depending on `color_lines`).
- Buffer counts in the tree reflect current-query matches (`3/173`) in addition to the file count.
