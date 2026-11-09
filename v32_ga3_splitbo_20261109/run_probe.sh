#!/bin/sh
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$root"
sh run_board.sh probe guard descending
sh run_board.sh probe guard ascending
echo 'PASS_PROBE_SCREEN: 16 windows, 3 measured plus 1 warmup per phase; CPU anchors included. First-trial uploads retained separately.'
