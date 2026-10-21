#!/bin/sh
# Stage and arm only after every existing board/snapshot check passes.
# This helper deliberately leaves reboot as a separate user command.
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
variant=${1:-raw_2_pipe}
action=${2:-check}
test "$#" -le 2 || exit 2
case "$variant" in raw_2_pipe|raw_2_full) ;;*) echo 'Expected raw_2_pipe or raw_2_full' >&2;exit 2;;esac
case "$action" in check|--check|arm|--arm) ;;*) echo 'Second argument must be check or arm' >&2;exit 2;;esac
sh "$root/check_package.sh"
sh "$root/stage_variant_board.sh" "$variant" --check
case "$action" in check|--check) echo 'CHECK_ONLY: hardware was not switched; no reboot request was armed.';exit 0;;esac
sh "$root/stage_variant_board.sh" "$variant"
sh "$root/prepare_variant_srst.sh" "$variant" --check
sh "$root/prepare_variant_srst.sh" "$variant"
echo 'ARMED_ONLY: after reviewing success, execute sync && reboot from the board terminal.'
