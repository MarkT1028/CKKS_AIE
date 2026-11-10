#!/bin/sh
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
python3 finish_board.py run direct2 smoke descending
for p in merge1 direct1 direct2 merge1; do
    python3 finish_board.py run "$p" pilot descending
done
python3 summarize_screen.py
echo 'SHORT_SCREEN_COMPLETE: return the archive before deciding on full1024 runs.'
