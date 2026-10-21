#!/bin/sh
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
reps=${1:-30}
variant=${2:-raw_1_pipe}
test "$#" -le 2 || exit 2
case "$variant" in raw_1_pipe|baseline_1) ;;*) echo 'Expected raw_1_pipe or baseline_1' >&2;exit 2;;esac
test "${PERF_PROFILE:-none}" = none || { echo 'Use profile-disabled runs for this comparison; unset PERF_PROFILE.' >&2;exit 2; }
PERF_PROFILE=none;export PERF_PROFILE
printf 'SINGLE_PIPE_TEST variant=%s repetitions=%s warmups=3; K1/K16 resident/transfer; no CPU benchmark.\n' "$variant" "$reps"
exec sh "$root/run_perf_board.sh" "$variant" "$reps"
