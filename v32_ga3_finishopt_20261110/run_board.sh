#!/bin/sh
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
exec python3 finish_board.py run "${1:-direct2}" "${2:-smoke}" "${3:-descending}"
