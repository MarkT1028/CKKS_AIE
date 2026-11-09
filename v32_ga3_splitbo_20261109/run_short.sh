#!/bin/sh
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$root"
python3 ga3_board.py detect
sh run_board.sh smoke guard descending
sh run_board.sh pilot guard descending
sh run_board.sh pilot guard ascending
echo 'PASS_SHORT_SCREEN: two orders, one hardware trial each; input copies/sync are inside timing. No reboot or full 1024-window campaign performed.'
echo 'NEXT: compare the SAME short screen on the other image; collect results before any long campaign.'
