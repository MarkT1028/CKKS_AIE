#!/bin/sh
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
variant=${1:-raw_1_pipe}
test "$#" -le 1 || exit 2
case "$variant" in raw_1_pipe|baseline_1) ;;*) echo 'Expected raw_1_pipe or baseline_1' >&2;exit 2;;esac
sh "$root/check_package.sh"
exec sh "$root/build_perf_board.sh" "$variant"
