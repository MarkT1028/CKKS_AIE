#!/bin/sh
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
diag_dir=$(pwd)
. ./diag_common.sh
diag_require
./ckks_mac_persistent_xrt --capabilities | grep -q '^PLIO_COUNTER_API=1$' || {
    echo 'COUNTER_API_UNAVAILABLE: baseline remains usable; use run_aie_profile_board.sh'; exit 2;
}
port=${1:-partials}
case "$port" in left|right|partials) ;; *) echo 'FAIL: port must be left, right or partials'; exit 1;; esac
root=$(mktemp -d ./plio_${port}_results_XXXXXXXX)
echo "PLIO_COUNTER_RESULTS=$root"
sh collect_board_env.sh > "$root/board_env.txt" 2>&1
k=16
diag_case
if ! XRT_INI_PATH="$diag_dir/configs/baseline.ini" ./ckks_mac_persistent_xrt \
     "$base/ckks_hw_boot.xclbin" "$input" "$expected" "$root/host" \
     resident 10 1 120000 "$port" > "$root/host.log" 2>&1; then
    cat "$root/host.log"; echo 'COUNTER_FAILED: no valid counter conclusion; download the result folder'; exit 2
fi
cat "$root/host.log"
cmp "$expected" "$root/host/output_last.bin"
echo "PASS PLIO COUNTER: raw cycle counts saved in $root/host/iterations.csv."
