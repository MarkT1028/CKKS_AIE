#!/bin/sh
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
test "$(uname -m)" = aarch64 || { echo 'Build on VEK280 ARM Linux.' >&2; exit 1; }
python3 "$root/board_runner.py" check
base=$(python3 "$root/board_runner.py" base-path)
mkdir -p "$root/bin"
g++ -O3 -std=c++17 -pthread "$root/reference/cpu/cached_cpu.cpp" -o "$root/bin/cached_cpu"
"$root/bin/cached_cpu" --self-test
g++ -O3 -std=c++17 -pthread "$root/tests/fake_backend.cpp" -o "$root/bin/schedule_selftest"
test_dir=$(mktemp -d "$root/bin/schedule_check.XXXXXXXX")
"$root/bin/schedule_selftest" "$root/test_fixture" "$test_dir/results" > "$root/bin/schedule_selftest.log" 2>&1
cat "$root/bin/schedule_selftest.log"
g++ -O3 -std=c++17 -pthread -I/usr/include/xrt "$root/host/bo_host.cpp" -lxrt_coreutil -o "$root/bin/bo_host"
"$root/bin/bo_host" --check-data "$base/fixture"
python3 "$root/board_runner.py" record-build
echo 'BUILD_READY: CPU arithmetic, host-only scheduling and full real mapped partitions checked. PL/AIE not executed; firmware unchanged.'
