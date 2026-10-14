#!/bin/sh
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
diag_dir=$(pwd)
. ./diag_common.sh
diag_require
metric=${1:-heat_map}
case "$metric" in heat_map|stalls|execution|input_stalls|output_stalls) ;;
    *) echo 'FAIL: choose heat_map, stalls, execution, input_stalls or output_stalls'; exit 1;;
esac
repetitions=${2:-200}
root=$(mktemp -d ./aie_${metric}_results_XXXXXXXX)
root=$(CDPATH= cd -- "$root" && pwd)
echo "AIE_PROFILE_RESULTS=$root"
sh collect_board_env.sh > "$root/board_env.txt" 2>&1
# A separate run for each metric; counter resources are finite.
k=16
diag_case
cp "configs/$metric.ini" "$root/xrt.ini"
# Keep the executable and working directory together for XRT output discovery.
cp ./ckks_mac_persistent_xrt "$root/ckks_mac_persistent_xrt"
cd "$root"
if ! XRT_INI_PATH="$root/xrt.ini" ./ckks_mac_persistent_xrt \
     "$base/ckks_hw_boot.xclbin" "$input" "$expected" "$root/host" \
     resident "$repetitions" 3 120000 > host.log 2>&1; then
    cat host.log; echo "FAIL: profile run stopped; files retained in $root"; exit 1
fi
cat host.log
cmp "$expected" "$root/host/output_last.bin"
find . -maxdepth 2 -type f -print > generated_files.txt
if find . -maxdepth 2 -type f \( -name '*aie*profile*.csv' -o -name 'profile_aie*.csv' \) | grep -q .; then
    echo "PROFILE_FILES_PRESENT: metric=$metric. Counter coverage still needs inspection."
else
    echo 'PROFILE_UNAVAILABLE: no AIE profile CSV was generated. Correctness PASS is not profiling PASS.'
    echo 'Download host.log, board_env.txt, xrt.ini and generated_files.txt for diagnosis.'
    exit 2
fi
echo "Download the entire $root folder including xrt.run_summary and all CSV/JSON files."
