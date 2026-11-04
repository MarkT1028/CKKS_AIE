#!/bin/sh
set -eu
native_root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
case "${1:-smoke}" in
 smoke) python3 "$native_root/window_board.py" smoke chunk export_bounded ;;
 formal)
  python3 "$native_root/window_board.py" formal chunk export_bounded
  python3 "$native_root/window_board.py" formal chunk export_bounded --reverse
  python3 "$native_root/compare_native_campaign.py"
  ;;
 *) echo 'usage: sh run_hs4_compare.sh smoke|formal' >&2;exit 1 ;;
esac
