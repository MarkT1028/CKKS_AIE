#!/bin/sh
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$root"
python3 ga3_board.py detect
for profile in baseline burst cacheable; do
    sh run_board.sh smoke "$profile" descending
done
for profile in baseline burst cacheable baseline; do
    sh run_board.sh probe "$profile" descending
done
python3 summarize_hostopt.py
echo 'SCREEN_COMPLETE: subset only; collect results before deciding full-run profile.'
