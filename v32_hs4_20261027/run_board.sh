#!/bin/sh
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
action=${1:?usage: sh run_board.sh smoke_OR_formal}
case "$action" in smoke|formal) ;;*) echo 'action must be smoke or formal' >&2;exit 2;;esac
exec python3 "$root/board_runner.py" "$action"
