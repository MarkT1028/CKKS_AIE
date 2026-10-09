#!/bin/sh
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
[ "$(uname -m)" = aarch64 ] || { echo 'FAIL: run on the VEK280 Linux board'; exit 1; }
sha256sum -c SHA256SUMS_PERF
sha256sum -c SHA256SUMS
sha256sum -c SHA256SUMS_K16
[ -x ./ckks_mac_timed_xrt ] && [ -x ./ckks_mac_cpu_bench ] || { echo 'FAIL: run sh build_perf_board.sh first'; exit 1; }
./ckks_mac_timed_xrt --inspect-xclbin ckks_hw_boot.xclbin
result_dir=$(mktemp -d ./perf_results_XXXXXXXX)
echo "PERF_RESULTS=$result_dir"
printf 'K,cpu_compute_median_ms,hw_execution_median_ms,hw_host_path_median_ms,cpu_over_hw_execution,cpu_over_hw_host_path\n' > "$result_dir/summary.csv"
for k in 1 16; do
    if [ "$k" = 1 ]; then input=inputs.bin; expected=expected_raw.bin
    else input=inputs_k16.bin; expected=expected_k16_raw.bin; fi
    echo "K=$k CPU: one warmup and three measured repetitions"
    if ! ./ckks_mac_cpu_bench "$input" "$expected" > "$result_dir/cpu_k$k.log" 2>&1; then
        cat "$result_dir/cpu_k$k.log"; exit 1
    fi
    cat "$result_dir/cpu_k$k.log"
    for repetition in 0 1 2 3; do
        echo "K=$k hardware repetition=$repetition (0 is warmup)"
        output="$result_dir/output_k${k}_r${repetition}.bin"
        log="$result_dir/hw_k${k}_r${repetition}.log"
        if ! ./ckks_mac_timed_xrt ckks_hw_boot.xclbin "$input" "$output" 120000 > "$log" 2>&1; then
            cat "$log"; exit 1
        fi
        cmp "$expected" "$output"
        grep '^TIMING ' "$log"
    done
    cpu_ms=$(awk '/^CPU_MEDIAN / {sub(/^compute_ms=/,"",$2); print $2}' "$result_dir/cpu_k$k.log")
    for field in execution_ms host_path_ms; do
        for repetition in 1 2 3; do
            awk -v key="$field" '/^TIMING / {for(i=2;i<=NF;i++){split($i,a,"=");if(a[1]==key)print a[2]}}' "$result_dir/hw_k${k}_r${repetition}.log"
        done | sort -n | sed -n '2p' > "$result_dir/median_k${k}_$field.txt"
    done
    hw_ms=$(cat "$result_dir/median_k${k}_execution_ms.txt")
    path_ms=$(cat "$result_dir/median_k${k}_host_path_ms.txt")
    awk -v k="$k" -v cpu="$cpu_ms" -v hw="$hw_ms" -v path="$path_ms" 'BEGIN {
        if(cpu<=0 || hw<=0 || path<=0) exit 1;
        printf "%d,%.6f,%.6f,%.6f,%.6f,%.6f\n",k,cpu,hw,path,cpu/hw,cpu/path;
    }' >> "$result_dir/summary.csv"
done
cat "$result_dir/summary.csv"
echo "PASS PERF: all CPU and hardware outputs verified. Results: $result_dir"
echo 'Measured scope: raw NTT/RNS MAC; file I/O and OpenFHE relin/rescale/decrypt are excluded.'
