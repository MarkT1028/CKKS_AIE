#!/bin/sh
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$root"
: "${V32_GA3_CACHE:=$root/../v32_ga3_compact_cache_pilot}"
export V32_GA3_CACHE
python3 compact_cache.py check
sh run_board.sh smoke sha256 descending
sh run_board.sh smoke packed descending
# Counterbalanced short request test. Each pilot covers all RNS shards and
# both boundary coefficient/output windows. All I/O and decoding is timed.
sh run_board.sh pilot sha256 descending
sh run_board.sh pilot packed descending
sh run_board.sh pilot packed ascending
sh run_board.sh pilot sha256 ascending
python3 summarize_compact.py
echo 'SCREEN_COMPLETE: collect the results; full-layer raw-MAC tests are a separate next step.'
