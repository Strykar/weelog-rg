#!/usr/bin/sh
# Drive a weelog script in weechat-headless and dump its results buffer.
#   scripts/weechat-e2e/run.sh WORKDIR LOGS_DIR 'CMD1;;CMD2;;...'
# WEELOG_SCRIPT: script to load (default weechat/weelog.py). "!CMD" fires without waiting.
# Output: WORKDIR/out.txt, one "epoch<TAB>prefix<TAB>message" per line under "### CMD".
set -eu
work=$1; logs=$2; cmds=$3
repo=$(cd "$(dirname "$0")/../.." && pwd)
mkdir -p "$work/home/python/autoload" "$work/cache"
printf '[file]\nauto_log = off\ninfo_lines = off\npath = "%s"\n' "$logs" > "$work/home/logger.conf"
ln -sfn "${WEELOG_SCRIPT:-$repo/weechat/weelog.py}" "$work/home/python/autoload/weelog.py"
cp "$repo/scripts/weechat-e2e/harness.py" "$work/home/python/autoload/harness.py"
rm -f "$work/out.txt"
XDG_CACHE_HOME="$work/cache" HARNESS_OUT="$work/out.txt" HARNESS_CMDS="$cmds" \
    env -u VIRTUAL_ENV PATH=/usr/local/bin:/usr/bin:/bin \
    timeout 300 weechat-headless --stdout --dir "$work/home" > "$work/weechat.log" 2>&1
cat "$work/out.txt"
