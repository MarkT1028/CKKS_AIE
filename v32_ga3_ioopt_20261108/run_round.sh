#!/bin/sh
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$root"
profile=${1:-legacy}
sh run_board.sh smoke "$profile" descending
sh run_board.sh windows "$profile" descending
sh run_board.sh windows "$profile" ascending
sh run_board.sh stream "$profile" descending
sh run_board.sh export "$profile" descending
python3 summarize_ioopt.py
echo 'PASS_ONE_HOSTOPT_ROUND: hardware unchanged; no reboot requested.'
