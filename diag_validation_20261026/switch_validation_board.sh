#!/bin/sh
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
sh "$root/check_package.sh"
exec sh "$root/comparison/switch_controlled_board.sh" "$@"
