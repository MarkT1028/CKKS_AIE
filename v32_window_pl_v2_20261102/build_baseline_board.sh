#!/bin/sh
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
test "$(uname -m)" = aarch64 || { echo 'Build on VEK280 ARM Linux.' >&2;exit 1; }
python3 "$root/full_board.py" code-check
mkdir -p "$root/bin"
g++ -O3 -std=c++17 -pthread "$root/cpu/full_cpu.cpp" -o "$root/bin/full_cpu"
"$root/bin/full_cpu" --self-test
g++ -O3 -std=c++17 -pthread -DCKKSMAC_PARSER_ONLY "$root/host/full_host.cpp" -o "$root/bin/full_parser"
g++ -O3 -std=c++17 -pthread -I/usr/include/xrt "$root/host/full_host.cpp" -lxrt_coreutil -o "$root/bin/full_host"
python3 "$root/full_board.py" record-build
echo 'BUILD_READY: full six-group CPU/host; no PL/AIE execution, boot write or reset.'
