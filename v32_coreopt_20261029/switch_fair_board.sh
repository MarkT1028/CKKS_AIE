#!/bin/sh
# Existing guarded stage/arm flow; reboot remains an explicit board command.
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
variant=${1:?usage: switch_fair_board.sh VARIANT check|arm}
action=${2:-check}
test "$#" -le 2
case "$variant" in raw_2_pipe|diag_2_pipe|v32_diag_2_pipe|v32_core_2_pipe) ;;*) echo 'invalid comparison variant' >&2;exit 2;;esac
case "$action" in check|arm) ;;*) echo 'action must be check or arm' >&2;exit 2;;esac
sh "$root/check_package.sh"
sh "$root/stage_variant_board.sh" "$variant" --check
test "$action" = arm || { echo 'CHECK_ONLY: no boot image changed and no reboot request armed';exit 0; }
sh "$root/stage_variant_board.sh" "$variant"
sh "$root/prepare_variant_srst.sh" "$variant" --check
sh "$root/prepare_variant_srst.sh" "$variant"
echo 'ARMED_ONLY: review the successful output, then run sync && reboot yourself.'
