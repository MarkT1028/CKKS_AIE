#!/bin/sh
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
sh "$root/build_baseline_board.sh"
g++ -O3 -std=c++17 -pthread "$root/cpu/stream_cpu.cpp" -o "$root/bin/stream_cpu"
"$root/bin/stream_cpu" --self-test
g++ -O3 -std=c++17 -pthread -DCKKSMAC_PARSER_ONLY "$root/host/stream_host.cpp" -o "$root/bin/stream_parser"
g++ -O3 -std=c++17 -pthread -I/usr/include/xrt "$root/host/stream_host.cpp" -lxrt_coreutil -o "$root/bin/stream_host"
python3 "$root/stream_board.py" record-build
echo 'BUILD_READY_STREAM: old baseline and new streaming CPU/host; no PL/AIE execution, boot write or reset.'
