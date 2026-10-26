# User guide

## The screen

```
┌─ filters ──────────────────────────────────────────────────────────┐
│ Search [_______] Nick(s) [_____] From [____] To [____] context [__] │
│ regex  case  events  archives  system   show  compact context hits only │
├─ tree ───────────┬─ results ───────────────────────────────────────┤
│ networks         │ when   ago   where        who     message       │
│ ▾ example-net    │ ...                                             │
│   #channel-one   │                                                 │
│                  │                                                 │
├──────────────────┴─ context (100 lines each side of the match) ────┤
│ >> 10:00:30  alice  good morning                                   │
│    10:01:00  bob    morning, https://example.org/path?q=1          │
└────────────────────────────────────────────────────────────────────┘
```

`F2` hides the filter card, `F4` the tree, `F3` the context pane. On a terminal under 100 columns the context pane starts hidden; under 70 the tree does too.

## What each chip does

The filter card has two rows. The top row is for inputs you type into. The bottom row is a chip strip you click on or tab through.

**Inputs (top row)**

| Field | What you put there |
| --- | --- |
| Search | The phrase you're looking for in messages. A regular expression if the `regex` chip is on. |
| Nick(s) | One or more nicks, separated by spaces or commas. Matches any of them. See [The Nick field](#the-nick-field). |
| From / To | A date range. Format is `YYYY-MM-DD`, inclusive. |
| context length | How many lines to show above and below a match in the context pane. Defaults to 100. |

**Chips (bottom row)**

Most chips are off by default. Tick them to opt in.

- **regex**: treat your Search as a regular expression. Off means plain text.
- **case**: case-sensitive. Off (default) matches any case.
- **events**: show join/part/quit/topic/mode lines. Off keeps the results to real conversation.
- **archives**: also search rotated, compressed logs, both `.gz` and `.zst`. Slower than live files; turn on when you want history.
- **system**: include the buffers that are not conversation: your ZNC bouncer's `*status` and `*controlpanel`, soju's `BouncerServ`, services such as ChanServ and NickServ, and WeeChat's own `core.weechat`, `chanmon`, `highmon` and `newsmon` buffers. The monitor buffers mirror lines from real channels, so leaving this off avoids double counting. Channels, private messages and server buffers are always searched.
- **compact**: show only time, where and message columns. Off shows when, ago, where, who and message.
- **context**: show or hide the context pane. Same as `F3`.
- **hits only**: once a search has results, the tree shows only the buffers that matched.

## Key bindings

| Key                | Action |
| ------------------ | ------ |
| `/`                | focus the Search field |
| `Ctrl+L`           | focus the networks / buffers tree |
| `Ctrl+P`           | command palette: themes and the actions below |
| `F2`               | toggle the filter card |
| `F3`               | toggle the context pane |
| `F4`               | toggle the tree |
| `Enter` (on a result) | open the file in `$PAGER` at the matched line |
| `y`                | copy the current row to the clipboard |
| `Y` (Shift+y)      | copy the focused pane as plain text: the tree, every result row, or the context window (one line per row, no colour codes) |
| `Ctrl+E`           | export current results to `/tmp` (confirm first) |
| `?`                | show the key bindings inside the app |
| `Ctrl+Q`           | quit. `Ctrl+C` does not quit; it only reminds you of `Ctrl+Q`. |
| `Tab` / `Shift+Tab` | cycle focus across filters / tree / results |
| `↑ ↓ ← →`          | move within the focused widget |
| `Space`            | toggle the focused chip |
| `PgUp` / `PgDn`    | page through the results table |

## Minimum input for a search to run

A search is only dispatched when you have given it at least one of:

- **Search text** (a substring or regex), or
- **a Nick** (matches that nick's own lines).

Other filters (tree selection, date range, chips) narrow or shape the results **after** a Search or Nick is set. On their own they never trigger a search, so opening the app and clicking through the tree without typing anything leaves the results pane empty by design.

| Goal                               | Minimum you must set         |
| ---------------------------------- | ---------------------------- |
| Find a phrase anywhere             | Search                       |
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

Results read top to bottom as a transcript.

**Find a command you ran weeks ago**

```
Search pacman -Syu
From   2025-10-01    To  2025-11-15
```

**One nick's messages across every channel**

```
Nick   someone
```

Empty Search is fine; the nick alone drives the search.

## The Nick field

Accepts any number of nicks, separated by spaces or commas. Whitespace is trimmed and empty entries are ignored.

Matching is anchored to the nick column, so `alice` never matches a message that merely mentions alice. Within that column it is fuzzy: every character you type must appear in the nick, in order, with anything in between. `alice` matches `alice` and also `alice_away` or `malice`; `ab` matches `abe` and `arbiter`. Type more of the nick to tighten it.

**Multiple nicks combine with OR, not AND.** `alice bob` returns lines written by alice *or* bob. Read chronologically that is a transcript of whichever of them was talking. There is no intersection mode.

| Input              | Matches                                             |
| ------------------ | --------------------------------------------------- |
| (empty)            | no nick filter; the Search drives the query alone   |
| `alice`            | lines whose nick contains a, l, i, c, e in that order |
| `alice bob`        | lines by a nick matching alice OR one matching bob  |
| `alice, bob, eve`  | same with three nicks                               |
| `  alice   bob  `  | same as `alice bob` (whitespace ignored)            |

Case follows the **case** chip: off (default) matches any case, on is exact.

If you log with a nick prefix or suffix (`logger.file.nick_prefix` / `nick_suffix`, for example `<alice>`), the tool reads them from your `logger.conf` so the Nick field still matches and the display shows the bare nick.

## The context pane

Moving onto a result shows what was said around that line: the matched line marked `>>`, with up to **context length** lines (default 100) above and below it. Long messages wrap within the message column; timestamps and nicks stay aligned.

The pane's header reads like:

```
Context: grep --context=100 --line-number --extended-regexp '…' 2026/<net>/<channel>.04-14.log  →  line 1234
```

It is a description in the familiar `grep` idiom, not a command to run: the number is the context length, `'…'` stands in for your Search, and the path and line are where the match came from. The real search engine is [ripgrep](https://github.com/BurntSushi/ripgrep); the pane itself reads the file directly, including `.gz` and `.zst` archives.

## Copying to the clipboard

The first `y` or `Y` of a session asks whether to enable clipboard writes. Say no and both keys do nothing until you restart. The tool never reads your clipboard.

Copies travel through the terminal (OSC 52), so the terminal has to support it; Kitty, WezTerm, foot, iTerm2 and Alacritty do. Under tmux the `set-clipboard` option must allow it. Payloads over about 70 KB are flagged because many terminals truncate them.

## Exporting results

`Ctrl+E` shows the destination and asks for confirmation, then writes the current results (at most 500 rows, see below) to `/tmp/weelog-rg-<timestamp>-<random>.tsv`. The file is created with mode 0600 and never replaces an existing file.

Columns are `timestamp`, `buffer`, `nick`, `message` and `source` (`file:line` relative to the logs directory), tab separated, with a `#` header line. Fields containing tabs, newlines or quotes are quoted the way a spreadsheet export is. A cell that starts with `=`, `+`, `-` or `@` gets a leading apostrophe so a spreadsheet will not run it as a formula; strip it if you process the file with other tools.

## Limits

- **500 hits.** The results pane stops at 500 and the title shows `500+ (truncated)`. Those are the first 500 ripgrep found, in file order (roughly newest year first for dated logs), not the 500 most recent. Narrow by nick, date or buffer.
- **Rotated logs can overlap.** With `archives` on, a rotated file and the live file can both hold lines from around the rotation point, so the same line may appear twice.
- **Non-conversation buffers** are off until you tick `system`, even if you select one in the tree.

## Visual cues

- **Nick colour** is stable across sessions (same nick, same colour).
- **Event lines** (join/part/topic/mode) render dim and only show when `events` is on.
- **Private messages** use a direction arrow in the where column: `← nick` incoming, `→ nick` outgoing. The arrow points at the author.
- **URLs** are linkified via OSC 8 except where the terminal already does it (Kitty, WezTerm, iTerm2, Ghostty, foot, VTE).

## Themes

```sh
weelog-rg --logs DIR --theme auto     # default; currently the same as dark
weelog-rg --logs DIR --theme dark
weelog-rg --logs DIR --theme light
weelog-rg --logs DIR --theme gruvbox
weelog-rg --logs DIR --theme catppuccin-mocha
```

Any Textual theme name works; `Ctrl+P` lets you switch live.
