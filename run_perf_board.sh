#!/bin/sh
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
variant=${1:?usage: run_perf_board.sh VARIANT [REPS=30] [FIXTURE_DIR]}
reps=${2:-30}
fixtures=${3:-$root/fixtures}
case "$variant" in baseline_1|sink_1|raw_1_pipe|raw_2_shared|raw_2_full|raw_2_pipe|diag_1_pipe|diag_2_pipe) ;; *) echo 'invalid variant' >&2;exit 2;;esac
case "$reps" in ''|*[!0-9]*) echo 'repetitions must be an integer' >&2;exit 2;;esac
test "$reps" -ge 1 && test "$reps" -le 10000
cd "$root"
sha256sum -c SHA256SUMS_PACKAGE
sha256sum -c "bin/perf_host_$variant.sha256"
sha256sum -c "bin/perf_host_$variant.sources.sha256"
host="$root/bin/perf_host_$variant"
xclbin="$root/variants/$variant/ckks_hw_boot.xclbin"
expected_uuid=$(cat "$root/variants/$variant/EXPECTED_BOOT_UUID")
marker=/sys/firmware/devicetree/base/chosen/ckks,boot-xclbin-uuid
test -f "$marker" || { echo 'BOOT_MARKER_MISSING; no kernels started' >&2;exit 2; }
actual_uuid=$(tr -d '\000\n\r' < "$marker")
test "$actual_uuid" = "$expected_uuid" || {
  echo "BOOT_MISMATCH expected=$expected_uuid actual=$actual_uuid; no kernels started" >&2
  exit 2
}
for name in inputs.bin expected_raw.bin inputs_k16.bin expected_k16_raw.bin;do test -s "$fixtures/$name";done
metric=${PERF_PROFILE:-none}
case "$metric" in none|out0|out1|in0|in1|heat_map|stalls) ;; *) echo 'PERF_PROFILE must be none/out0/out1/in0/in1/heat_map/stalls' >&2;exit 2;;esac
result=$(mktemp -d "$root/results_${variant}_${metric}_XXXXXXXX")
cp "$root/variants/$variant/manifest.json" "$result/variant_manifest.json"
sha256sum "$fixtures/inputs.bin" "$fixtures/expected_raw.bin" "$fixtures/inputs_k16.bin" "$fixtures/expected_k16_raw.bin" > "$result/fixture_sha256.txt"
uname -a > "$result/board_env.txt"
date -u '+UTC=%Y-%m-%dT%H:%M:%SZ' >> "$result/board_env.txt"
sha256sum "$host" "$xclbin" >> "$result/board_env.txt"
cat /proc/loadavg >> "$result/board_env.txt"
if test -r "$root/bin/perf_host_$variant.build.txt";then cp "$root/bin/perf_host_$variant.build.txt" "$result/host_build.txt";fi
sed -n '/^MemTotal:/p;/^MemAvailable:/p;/^CmaTotal:/p;/^CmaFree:/p' /proc/meminfo >> "$result/board_env.txt"
for perf_sysfile in /sys/devices/system/cpu/cpufreq/policy*/scaling_cur_freq /sys/devices/system/cpu/cpufreq/policy*/scaling_governor;do
  if test -r "$perf_sysfile";then printf '%s=' "$perf_sysfile" >> "$result/board_env.txt";cat "$perf_sysfile" >> "$result/board_env.txt";fi
done
printf 'RESULTS=%s\n' "$result"
for k in 1 16;do
  if test "$k" -eq 1;then input="$fixtures/inputs.bin";expected="$fixtures/expected_raw.bin";else input="$fixtures/inputs_k16.bin";expected="$fixtures/expected_k16_raw.bin";fi
  "$host" --preflight "$xclbin" "$input" "$expected"
  modes='resident transfer'
  if test "$metric" != none;then modes=resident;fi
  for mode in $modes;do
    case_dir="$result/k${k}_$mode"
    mkdir "$case_dir"
    if test "$metric" = none;then
      printf '[Debug]\naie_profile=false\naie_trace=false\n' > "$case_dir/xrt.ini"
    elif test "$metric" = heat_map || test "$metric" = stalls;then
      printf '[Debug]\naie_profile=true\naie_trace=false\n[AIE_profile_settings]\ninterval_us=2000\ngraph_based_aie_metrics=ckks_graph:all:%s\n' "$metric" > "$case_dir/xrt.ini"
      if test "$metric" = heat_map;then printf 'graph_based_aie_memory_metrics=ckks_graph:all:conflicts\n' >> "$case_dir/xrt.ini";fi
    else
      case "$metric" in out*) event=mm2s_throughputs;;in*) event=s2mm_throughputs;;esac
      case "$metric" in *0) channel=0;;*1) channel=1;;esac
      printf '[Debug]\naie_profile=true\naie_trace=false\n[AIE_profile_settings]\ninterval_us=2000\ngraph_based_aie_metrics=ckks_graph:all:%s:%s\ngraph_based_aie_memory_metrics=ckks_graph:all:%s:%s\n' "$event" "$channel" "$event" "$channel" > "$case_dir/xrt.ini"
    fi
    export XRT_INI_PATH="$case_dir/xrt.ini"
    # No pipeline through tee: preserve program failure status on POSIX sh.
    if (cd "$case_dir" && "$host" "$xclbin" "$input" "$expected" "$case_dir/host" "$reps" 3 "$mode" run > host.log 2>&1);then
      cat "$case_dir/host.log"
    else
      cat "$case_dir/host.log"
      printf 'FAILED_STOPPED; do not continue after an incomplete hardware run\n' > "$result/STATUS.txt"
      exit 1
    fi
  done
done
printf 'PASS_ALL_REQUESTED_CASES\n' > "$result/STATUS.txt"
echo "DOWNLOAD_ENTIRE_RESULTS=$result"
