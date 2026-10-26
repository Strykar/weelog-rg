# User guide

## The screen

```
┌─ filters ─────────────────────────────────────────────────────────┐
│  Query  [_______]   regex  case  hide events  archives            │
│  Nick   [_______]   From [____]  To [____]                        │
│  Columns  date  ago  channel  nick   |  clipboard  context        │
├─ tree ───────────┬─ results ──────────────────────────────────────┤
│  networks        │  when   ago   where      nick    message       │
│  ▾ example-net   │  ...                                           │
│    #channel-one  │                                                │
│  core            │                                                │
│                  │                                                │
├──────────────────┴─ context (±40 lines around selected result) ───┤
│  >> 10:00:30  alice  good morning                                 │
│     10:01:00  bob    morning, https://example.org/path?q=1        │
└───────────────────────────────────────────────────────────────────┘
```

## What each chip does

The filter card has two rows. The top row is for inputs you type into. The bottom row is a chip strip you click on or tab through.

**Inputs (top row)**

| Field | What you put there |
| --- | --- |
| Search | The phrase you're looking for in messages. |
| Nick(s) | One or more nicks, separated by spaces or commas. Matches any of them. |
| From / To | A date range. Format is `YYYY-MM-DD`. |
| Context length | How many lines to show above and below each match in the Context pane. Defaults to 100. |

**Chips (bottom row)**

Most chips are off by default. Tick them to opt in.

- **regex**: treat your Search as a regex. Off means plain text.
- **case**: case-sensitive. Off uses smart case (lowercase input matches anything).
- **events**: show join/part/quit/topic/mode lines. Off keeps your results focused on real conversation.
- **archives**: also search rotated, compressed logs. Both `.gz` and `.zst` (the two compression types WeeChat's logger supports). Slower than searching live files; turn on when you want history.
- **meta**: include WeeChat's monitor buffers (`chanmon`, `highmon`, `newsmon`) and `core.weechat`. These mirror messages from real channels, so leaving this off avoids double-counting.
- **znc**: include your ZNC bouncer buffers (`*status`, `*controlpanel`, etc.).
- **soju**: placeholder; soju buffers aren't classified yet (open a PR with sample logs).
- **services**: include automated network services (ChanServ, NickServ, MemoServ, OperServ, etc.).
- **date / ago / chan / nick**: show or hide the corresponding column in the results pane. The message column is always shown.
- **context**: show or hide the Context pane.
- **clipboard**: your clipboard is not read until you tick this. Once on, `y` and `Y` work.

## Key bindings

| Key                | Action |
| ------------------ | ------ |
| `/`                | focus the Query field |
| `Ctrl+L`           | focus the Networks / Buffers tree |
| `Ctrl+P`           | command palette (themes, actions, commands) |
| `Enter` (on a result) | open the day-file in `$PAGER` at the matched line |
| `y`                | yank the current row to the clipboard |
| `Y` (Shift+y)      | yank the entire context window to the clipboard as plain text (no colour codes, one line per row). Useful when a terminal mouse-drag would pick up whitespace from neighbouring panes. |
| `Ctrl+E`           | export current results to `/tmp` (confirm first) |
| `Ctrl+Q`           | quit |
| `Tab` / `Shift+Tab` | cycle focus across filters / tree / results |
| `↑ ↓ ← →`          | move within the focused widget |
| `Space`            | toggle the focused checkbox |
| `PgUp` / `PgDn`    | page through the results table |

## Minimum input for a search to run

weelog-rg will not scan logs on every keystroke. A search is only dispatched when you have given it at least one of:

- **Query text** (any body substring or regex), or
- **a Nick** (anchored, matches that nick's own lines).

Other filters (network tree selection, date range, `archives`, `hide events`, and the column toggles) narrow or shape the results **after** a Query or Nick is set. On their own they never trigger a search, so opening the app and clicking through the network tree without typing anything will leave the Results pane empty by design.

Typical minima that produce meaningful output:

| Goal                               | Minimum you must set         |
| ---------------------------------- | ---------------------------- |
| Find a phrase anywhere             | Query                        |
| Read one nick's messages           | Nick                         |
| Transcript between two nicks       | Nick `alice bob`             |
| Constrain any of the above by time | add From / To                |
| Constrain any of the above by room | click a channel in the tree  |

## Typical workflows

**Conversation between two people in a busy channel**

```
tree   click the channel under its network
Nick   alice bob
```

Results read top-to-bottom as a transcript.

**Find a command you ran weeks ago**

```
Query  pacman -Syu
From   2025-10-01    To  2025-11-15
```

**One nick's messages across every channel**

```
Nick   someone
```

Empty Query is fine; the nick alone drives the search.

## The Context pane

When you click or cursor onto a result row, the Context pane shows you what was being said **around** that line. Think of it as opening the log file at the matched line and scrolling 40 lines up and 40 lines down. You see the conversation the match is part of, with the matched line marked `>>` and coloured.

Long messages wrap within the message column; timestamps and nicks stay aligned.

The header of the pane reads something like:

```
Context: grep --context=100 --line-number --extended-regexp '…' 2026/<net>/<channel>.04-14.log  →  line 1234
```

That header is a plain-English description of what you are looking at, written in the familiar `grep` idiom:

- `--context=100`: show 100 lines before and 100 lines after the match
- `--line-number`: lines are numbered in the source file
- `--extended-regexp`: the search pattern is an extended regex
- `'…'`: stands in for your actual Query (elided to keep the header short)
- the file path and `→ line 1234` point at the file and line the match came from

The header is a label, not a command to run. The real search engine is [ripgrep](https://github.com/BurntSushi/ripgrep); the pane's contents come from reading the file directly (including `.gz` and `.zst` archives).

## Visual cues

- **Nick colour** is stable across sessions (same nick, same colour).
- **Event lines** (join/part/topic/mode) render dim; they don't show at all when `hide events` is on.
- **Private messages** use a direction arrow in the channel column: `← nick` incoming, `→ nick` outgoing. The arrow points at the author.
- **URLs** are linkified via OSC 8 except where the terminal already auto-linkifies (Kitty, WezTerm, iTerm2, Ghostty, foot, VTE).

## The Nick field

Accepts any number of nicks, separated by spaces or commas. Leading and trailing whitespace is trimmed; empty entries are ignored. The field is anchored between tab characters in the underlying search, so `alice` matches only alice's own lines, not messages that mention alice.

**How multiple nicks combine: OR, not AND.** Listing `alice bob` returns lines written by alice *or* bob, never a single line jointly written by both (that's not a thing in IRC). Viewed chronologically, the results read as a transcript of whichever of the listed nicks was talking. There is no intersection mode.

Semantics at a glance:

| Input              | Matches                                             |
| ------------------ | --------------------------------------------------- |
| (empty)            | no nick filter; the Query drives the search alone   |
| `alice`            | lines where alice is the author                     |
| `alice bob`        | lines by alice OR bob                               |
| `alice, bob, eve`  | lines by alice OR bob OR eve                        |
| `  alice   bob  `  | same as `alice bob` (whitespace ignored)            |

Case handling follows the **case** checkbox: off (default) is smart-case (lowercase input matches any case), on is exact.

Limits: no hard cap on nick count. A huge list eventually runs into ripgrep's regex length, but for any realistic set (dozens of nicks) this is nowhere near reachable. The anchored regex keeps scanning linear in log size regardless of the nick list size.

## Themes

```sh
weelog-rg --logs DIR --theme auto     # default; reads $COLORFGBG
weelog-rg --logs DIR --theme dark
weelog-rg --logs DIR --theme light
weelog-rg --logs DIR --theme gruvbox
weelog-rg --logs DIR --theme catppuccin-mocha
```

Any Textual-supported theme name works; `Ctrl+P` lets you switch live.
