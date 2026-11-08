#!/bin/sh
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$root"
echo 'This candidate starts with a short matched screen. See START_HERE.md.'
exec sh "$root/run_screen.sh"
