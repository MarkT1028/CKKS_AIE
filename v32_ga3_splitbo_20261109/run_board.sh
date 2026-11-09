#!/bin/sh
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$root"
mode=${1:-smoke}
profile=${2:-guard}
order=${3:-descending}
export V32_GA3_PROFILE="$profile"
python3 ga3_board.py run "$mode" "$order"
