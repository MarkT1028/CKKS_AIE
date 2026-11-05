#!/bin/sh
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec python3 "$root/ga3_board.py" run "${1:-smoke}" "${2:-descending}"
