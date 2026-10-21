#!/bin/sh
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
reps=${1:-30}
variant=${2:-raw_2_pipe}
test "$#" -le 2 || exit 2
case "$variant" in raw_2_pipe|raw_2_full) ;;*) echo 'Expected raw_2_pipe or raw_2_full' >&2;exit 2;;esac
test "${PERF_PROFILE:-none}" = none || { echo 'Use profile-disabled runs for this comparison; unset PERF_PROFILE.' >&2;exit 2; }
PERF_PROFILE=none;export PERF_PROFILE
printf 'REDUCER_TEST variant=%s repetitions=%s warmups=3; K1/K16 resident/transfer; no CPU benchmark.\n' "$variant" "$reps"
exec sh "$root/run_perf_board.sh" "$variant" "$reps"
