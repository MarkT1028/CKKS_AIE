#!/bin/sh
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
kind=${1:-formal}
case "$kind" in smoke|formal) ;;*) echo 'usage: sh run_compare_layouts.sh smoke|formal' >&2;exit 2;;esac
# Same current boot/backend throughout. Every command has CPU before/after.
sh "$root/run_window_board.sh" "$kind" group retain
sh "$root/run_window_board.sh" "$kind" chunk retain
sh "$root/run_window_board.sh" "$kind" chunk export_bounded
sh "$root/run_window_board.sh" "$kind" chunk export_bounded --reverse
echo 'PASS_CURRENT_BOOT_LAYOUT_MATRIX: collect only after completing both requested backends; no reboot performed.'
