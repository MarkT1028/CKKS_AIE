#!/bin/sh
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
test "$(uname -m)" = aarch64 || { echo 'Run this build on the VEK280 ARM Linux board.' >&2;exit 1; }
sh "$root/check_package.sh"
mkdir -p "$root/bin"
g++ -O3 -std=c++17 -pthread "$root/cpu/tiled_cpu.cpp" -o "$root/bin/tiled_cpu"
"$root/bin/tiled_cpu" --self-test
g++ -O3 -std=c++17 -pthread -I/usr/include/xrt "$root/host/tiled_host.cpp" -lxrt_coreutil -o "$root/bin/tiled_host"
"$root/bin/tiled_host" --check-data "$root/fixture"
python3 "$root/board_runner.py" record-build
echo 'BUILD_READY: CPU self-tests and full chunk parser/split/merge only; hardware was not executed.'
