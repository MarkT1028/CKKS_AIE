#!/bin/sh
# Add-on for the existing diag_20261014 package; does not replace its files.
set -eu
addon_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
selection=${1:-out0}
repetitions=${2:-20}
if [ "$#" -gt 2 ]; then
    echo 'Usage: sh run_memory_dma_profile_board.sh out0|out1|in0|in1|all [1..1000]'
    exit 1
fi
case "$selection" in out0|out1|in0|in1|all) ;; *) echo 'FAIL: choose out0, out1, in0, in1 or all'; exit 1;; esac
case "$repetitions" in ''|*[!0-9]*) echo 'FAIL: repetitions must be 1..1000'; exit 1;; esac
if [ "${#repetitions}" -gt 4 ] || [ "$repetitions" -lt 1 ] || [ "$repetitions" -gt 1000 ]; then
    echo 'FAIL: repetitions must be 1..1000'; exit 1
fi

cd "$addon_dir"
sha256sum -c SHA256SUMS_DMA
diag_dir=${CKKS_DIAG_DIR:-$(CDPATH= cd -- "$addon_dir/.." && pwd)}
diag_dir=$(CDPATH= cd -- "$diag_dir" && pwd)
[ -r "$diag_dir/diag_common.sh" ] || {
    echo 'FAIL: upload this entire add-on folder under diag_20261014, or set CKKS_DIAG_DIR'; exit 1;
}
cd "$diag_dir"
. ./diag_common.sh
diag_require

root=$(mktemp -d "$addon_dir/memory_dma_results_XXXXXXXX")
echo "MEMORY_DMA_RESULTS=$root"
printf 'PRECHECK_COMPLETE\n' > "$root/STATUS.txt"
sh "$diag_dir/collect_board_env.sh" > "$root/board_env.txt" 2>&1
sha256sum "$diag_dir/ckks_mac_persistent_xrt" > "$root/executable_sha256.txt"
cp "$addon_dir/SHA256SUMS_DMA" "$root/addon_SHA256SUMS_DMA"
printf 'selection=%s\nrepetitions=%s\nwarmups=3\nmode=resident\nnative_counter_port=none\n' \
    "$selection" "$repetitions" > "$root/request.txt"
k=16
diag_case
if [ "$selection" = all ]; then cases='out0 out1 in0 in1'; else cases=$selection; fi

for name in $cases; do
    case "$name" in
        out0) metric=mm2s_throughputs; channel=0; event_a=1037; event_b=1041;;
        out1) metric=mm2s_throughputs; channel=1; event_a=1038; event_b=1042;;
        in0)  metric=s2mm_throughputs; channel=0; event_a=1031; event_b=1039;;
        in1)  metric=s2mm_throughputs; channel=1; event_a=1032; event_b=1040;;
    esac
    case_dir="$root/$name"
    mkdir "$case_dir"
    printf 'HOST_NOT_STARTED\n' > "$case_dir/STATUS.txt"
    # Configure the local AIE core/memory modules only. No shim-tile metrics.
    # A channel suffix applies to this local DMA, not the PLIO stream ID.
    {
        printf '[Debug]\naie_profile=true\naie_trace=false\n'
        printf '[AIE_profile_settings]\ninterval_us=1000\n'
        printf 'graph_based_aie_metrics=ckks_graph:all:%s:%s\n' "$metric" "$channel"
        printf 'graph_based_aie_memory_metrics=ckks_graph:all:%s:%s\n' "$metric" "$channel"
    } > "$case_dir/xrt.ini"
    cp "$diag_dir/ckks_mac_persistent_xrt" "$case_dir/ckks_mac_persistent_xrt"
    echo "RUNNING: $name metric=$metric channel=$channel measured=$repetitions warmups=3"
    # Native PLIO profiling is explicitly off; the original guarded host path
    # continues to check every output word on every repetition.
    if (cd "$case_dir" && XRT_INI_PATH="$case_dir/xrt.ini" ./ckks_mac_persistent_xrt \
        "$base/ckks_hw_boot.xclbin" "$input" "$expected" "$case_dir/host" \
        resident "$repetitions" 3 120000 none > host.log 2>&1); then
        cat "$case_dir/host.log"
    else
        cat "$case_dir/host.log"
        printf 'HOST_FAILED\n' > "$case_dir/STATUS.txt"
        printf 'HOST_FAILED:%s\n' "$name" > "$root/STATUS.txt"
        echo "FAIL: results retained at $root; no reset or retry was performed."
        exit 2
    fi
    if ! grep -q 'PASS PERSISTENT: every repetition matched the full expected payload' "$case_dir/host.log"; then
        printf 'HOST_PASS_MARKER_MISSING\n' > "$case_dir/STATUS.txt"
        printf 'HOST_PASS_MARKER_MISSING:%s\n' "$name" > "$root/STATUS.txt"
        echo "FAIL: missing host correctness marker; preserve $root"; exit 2
    fi
    if ! cmp "$expected" "$case_dir/host/output_last.bin"; then
        printf 'LAST_OUTPUT_MISMATCH\n' > "$case_dir/STATUS.txt"
        printf 'LAST_OUTPUT_MISMATCH:%s\n' "$name" > "$root/STATUS.txt"
        echo "FAIL: final output mismatch; preserve $root"; exit 2
    fi
    profile=
    for candidate in "$case_dir"/*aie*profile*.csv "$case_dir"/profile_aie*.csv; do
        if [ -f "$candidate" ]; then profile=$candidate; break; fi
    done
    if [ -z "$profile" ]; then
        printf 'PROFILE_MISSING\n' > "$case_dir/STATUS.txt"
        printf 'PROFILE_MISSING:%s\n' "$name" > "$root/STATUS.txt"
        echo "PROFILE_UNAVAILABLE: hardware answers passed; no profile CSV. Download $root"; exit 2
    fi
    # Hardware-generation-2 physical IDs, with the XRT memory offset of 1000.
    # Check actual METRIC_DATA rows, not just the metric names in the header.
    if awk -F, -v expected_a="$event_a" -v expected_b="$event_b" '
        /^METRIC_DATA/ { data=1; next }
        data && $1 == "timestamp" { next }
        data && $2 == 17 {
            event=$4+0
            if (event == expected_a || event == expected_b) {
                seen[event]=1; memory_rows++
                if (($7+0) != 0) nonzero_memory_rows++
            }
            if (event >= 75 && event <= 103 && (event-75)%4 == 0) running_rows++
            if (event >= 76 && event <= 104 && (event-76)%4 == 0) stalled_rows++
            if (event >= 2000 && event < 3000) shim_rows++
        }
        END {
            printf "MEMORY_EVENT_IDS=%d,%d\nMEMORY_ROWS=%d\nNONZERO_MEMORY_ROWS=%d\nCORE_RUNNING_ROWS=%d\nCORE_STALLED_ROWS=%d\nSHIM_ROWS=%d\n",
                   expected_a,expected_b,memory_rows,nonzero_memory_rows,running_rows,stalled_rows,shim_rows
            if (!seen[expected_a] || !seen[expected_b] || !running_rows || !stalled_rows || shim_rows) exit 1
        }
    ' "$profile" > "$case_dir/counter_coverage.txt"; then
        cat "$case_dir/counter_coverage.txt"
    else
        cat "$case_dir/counter_coverage.txt"
        printf 'COUNTER_COVERAGE_FAILED\n' > "$case_dir/STATUS.txt"
        printf 'COUNTER_COVERAGE_FAILED:%s\n' "$name" > "$root/STATUS.txt"
        echo "PROFILE_COVERAGE_FAILED: hardware answers passed; requested counters not confirmed. Download $root"; exit 2
    fi
    printf 'ANSWERS_PASS_COUNTER_ROWS_PRESENT\n' > "$case_dir/STATUS.txt"
    (cd "$case_dir" && find . -maxdepth 2 -type f -print) > "$case_dir/generated_files.txt"
    echo "PROFILE_COUNTER_ROWS_PRESENT: $name. Zero activity can mean an unused channel; interpretation still requires analysis."
done
printf 'ANSWERS_PASS_REQUESTED_COUNTER_ROWS_PRESENT\n' > "$root/STATUS.txt"
echo "MEMORY_DMA_COMPLETE: download the entire $root folder."
