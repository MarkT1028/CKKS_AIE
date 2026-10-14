#!/bin/sh
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
diag_dir=$(pwd)
. ./diag_common.sh
diag_require
repetitions=${1:-30}
root=$(mktemp -d ./persistent_results_XXXXXXXX)
echo "PERSISTENT_RESULTS=$root"
sh collect_board_env.sh > "$root/board_env.txt" 2>&1
for k in 1 16; do
    diag_case
    ./ckks_mac_cpu_bench "$input" "$expected" > "$root/cpu_k$k.log" 2>&1
    cat "$root/cpu_k$k.log"
    for mode in resident transfer; do
        case_dir="$root/k${k}_$mode"
        echo "Running K=$k mode=$mode with three warmups and $repetitions measured repetitions"
        if ! XRT_INI_PATH="$diag_dir/configs/baseline.ini" ./ckks_mac_persistent_xrt \
             "$base/ckks_hw_boot.xclbin" "$input" "$expected" "$case_dir" \
             "$mode" "$repetitions" 3 120000 > "$root/k${k}_$mode.log" 2>&1; then
            cat "$root/k${k}_$mode.log"; echo "FAIL: partial results retained in $root"; exit 1
        fi
        cat "$root/k${k}_$mode.log"
        cmp "$expected" "$case_dir/output_last.bin"
        if [ "$k" = 1 ] && [ "$mode" = resident ]; then cat "$case_dir/summary.csv" > "$root/summary.csv"
        else tail -n 1 "$case_dir/summary.csv" >> "$root/summary.csv"; fi
    done
done
cat "$root/summary.csv"
echo "PASS PERSISTENT SUITE: four cases verified; download the entire $root folder."
