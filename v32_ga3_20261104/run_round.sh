#!/bin/sh
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$root"
python3 ga3_board.py detect
sh run_board.sh smoke
sh run_board.sh windows descending
sh run_board.sh windows ascending
sh run_board.sh stream descending
sh run_board.sh export descending
echo 'PASS_GA3_ONE_BOOT_ROUND: no reboot performed. Follow START_HERE for the next variant.'
