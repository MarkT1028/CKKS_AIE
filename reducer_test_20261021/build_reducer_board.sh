#!/bin/sh
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
variant=${1:-raw_2_pipe}
case "$variant" in raw_2_pipe|raw_2_full) ;;*) echo 'usage: sh build_reducer_board.sh [raw_2_pipe|raw_2_full]' >&2;exit 2;;esac
sh "$root/check_package.sh"
exec sh "$root/build_perf_board.sh" "$variant"
