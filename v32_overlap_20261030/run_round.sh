#!/bin/sh
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
variant=${1:-v32_core_2_pipe}
campaign=${2:-host}
case "$campaign" in host|ablation) ;; *) echo 'campaign: host or ablation' >&2;exit 1;; esac
python3 "$root/board_runner.py" smoke "$variant" --campaign "$campaign"
python3 "$root/board_runner.py" formal "$variant" --campaign "$campaign"
python3 "$root/board_runner.py" formal "$variant" --campaign "$campaign" --reverse
python3 "$root/cpu_diagnostics.py"
python3 "$root/summarize_campaign.py"
echo 'ROUND_COMPLETE: retain this folder and collect_results.py after all planned rounds.'
