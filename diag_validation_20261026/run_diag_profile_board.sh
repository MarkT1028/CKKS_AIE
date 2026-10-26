#!/bin/sh
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec python3 "$root/diag_profile_board.py" "$@"
