#!/bin/sh
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$root"
python3 ga3_board.py detect
for profile in legacy sequential; do
    sh run_board.sh smoke "$profile" descending
done
if python3 probe_crypto.py --available; then
    sh run_board.sh smoke sha256 descending
fi
sh run_board.sh pilot legacy descending
sh run_board.sh pilot sequential descending
if python3 probe_crypto.py --available; then
    sh run_board.sh pilot sha256 descending
fi
sh run_board.sh pilot legacy descending
python3 summarize_ioopt.py
echo 'SCREEN_COMPLETE: exact word-comparison and full-output SHA256 protocols are separate. Collect before full runs.'
