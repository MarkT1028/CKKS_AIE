#!/bin/sh
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
test "$(uname -m)" = aarch64 || { echo 'Build on VEK280 ARM Linux.' >&2; exit 1; }
python3 "$root/board_runner.py" check
base=$(python3 "$root/board_runner.py" base-path)
mkdir -p "$root/bin"
g++ -O3 -std=c++17 -pthread "$root/baseline/cpu/tiled_cpu.cpp" -o "$root/bin/baseline_cpu"
g++ -O3 -std=c++17 -pthread "$root/cpu/cached_cpu.cpp" -o "$root/bin/cached_cpu"
"$root/bin/baseline_cpu" --self-test
"$root/bin/cached_cpu" --self-test
g++ -O3 -std=c++17 -pthread -I/usr/include/xrt "$root/baseline/host/tiled_host.cpp" -lxrt_coreutil -o "$root/bin/baseline_host"
g++ -O3 -std=c++17 -pthread -I/usr/include/xrt "$root/host/cached_host.cpp" -lxrt_coreutil -o "$root/bin/cached_host"
"$root/bin/cached_host" --check-data "$base/fixture"
python3 "$root/board_runner.py" record-build
echo 'BUILD_READY: CPU self-tests; full fixture canonical parsing, scalar/block split and merge passed. PL/AIE not executed; firmware unchanged.'
