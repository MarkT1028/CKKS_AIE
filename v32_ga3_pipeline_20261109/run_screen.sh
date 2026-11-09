#!/bin/sh
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$root"
: "${V32_GA3_CACHE:=$root/../v32_ga3_compact_cache_pilot}"
export V32_GA3_CACHE
order=${1:-descending}
python3 compact_cache.py check
sh run_board.sh smoke baseline "$order"
sh run_board.sh smoke combined "$order"
sh run_board.sh pilot baseline "$order"
for profile in guard read1 read16 prefetch combined;do
    sh run_board.sh pilot "$profile" "$order"
done
sh run_board.sh pilot baseline "$order"
python3 summarize_pipeline.py
echo 'SCREEN_COMPLETE: return the result archive; all candidates and regressions retained.'
