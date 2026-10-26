"""Core of weelog-rg: index, query, ripgrep runner and log-line parser.

No UI dependencies, so the same code serves the Textual TUI and the WeeChat script.
"""
from .index import (
    LogFile,
    WriteRefused,
    build_index,
    cache_path,
    classify_buffer,
    index_key,
    load_index,
    load_or_build_index,
    set_write_policy,
)
from .parse import (
    context_groups,
    context_lines,
    extract_date,
    parse_line,
    parse_timestamp,
    read_weechat_nick_wrappers,
    strip_weechat_colors,
)
from .query import Query, parse_date, select_files
from .search import CHUNK, Match, match_from_rg, match_sort_key, rg_args, run_search

__all__ = [
    "CHUNK", "LogFile", "Match", "Query", "WriteRefused", "build_index", "cache_path",
    "classify_buffer", "context_groups", "context_lines", "extract_date", "index_key", "load_index",
    "load_or_build_index",
    "match_from_rg", "match_sort_key", "parse_date", "parse_line", "parse_timestamp",
    "read_weechat_nick_wrappers", "rg_args", "run_search", "select_files",
    "set_write_policy", "strip_weechat_colors",
]
