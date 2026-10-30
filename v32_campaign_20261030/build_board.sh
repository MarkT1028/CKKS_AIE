#!/bin/sh
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
test "$(uname -m)" = aarch64 || { echo 'Build on VEK280 ARM Linux.' >&2;exit 1; }
python3 "$root/board_runner.py" check
base=$(python3 "$root/board_runner.py" base-path)
mkdir -p "$root/bin"
g++ -O3 -std=c++17 -pthread "$root/reference/cpu/cached_cpu.cpp" -o "$root/bin/cached_cpu"
"$root/bin/cached_cpu" --self-test
g++ -O3 -std=c++17 -pthread "$root/tests/fake_backend.cpp" -o "$root/bin/schedule_selftest"
g++ -O3 -std=c++17 -pthread "$root/tests/finish_overlap_test.cpp" -o "$root/bin/finish_overlap_selftest"
test_dir=$(mktemp -d "$root/bin/schedule_check.XXXXXXXX")
"$root/bin/schedule_selftest" "$root/test_fixture" "$test_dir/baseline" > "$root/bin/schedule_selftest.log" 2>&1
"$root/bin/finish_overlap_selftest" "$root/test_fixture" "$test_dir/overlap" > "$root/bin/finish_overlap_selftest.log" 2>&1
"$root/bin/finish_overlap_selftest" "$root/test_fixture_edge" "$test_dir/edge" >> "$root/bin/finish_overlap_selftest.log" 2>&1
cat "$root/bin/schedule_selftest.log" "$root/bin/finish_overlap_selftest.log"
for variant in v32_diag_2_pipe v32_aie_only_2_pipe v32_reducer_only_2_pipe v32_core_2_pipe;do
  g++ -O3 -std=c++17 -pthread -I/usr/include/xrt "$root/variants/$variant/host/bo_host.cpp" -lxrt_coreutil -o "$root/bin/bo_host_$variant"
  "$root/bin/bo_host_$variant" --check-data "$base/fixture"
  echo "BUILD_READY=$root/bin/bo_host_$variant"
done
python3 "$root/board_runner.py" record-build
echo 'BUILD_READY: CPU self-test, async scheduling and full mapped partitions checked. No PL/AIE execution, boot write or reboot performed.'
