#!/bin/sh
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec python3 "$root/validation_board.py" cpu-aa "$@"
