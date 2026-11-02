#!/bin/sh
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$root"
python3 -c 'import full_board;full_board.board()'
python3 "$root/full_board.py" code-check >/dev/null
python3 "$root/window_board.py" code-check >/dev/null
sh "$root/build_stream_baseline.sh"
g++ -O3 -std=c++17 -pthread "$root/cpu/window_cpu.cpp" -o "$root/bin/window_cpu"
"$root/bin/window_cpu" --self-test
g++ -O3 -std=c++17 -pthread -DCKKSMAC_PARSER_ONLY "$root/host/window_host.cpp" -o "$root/bin/window_parser"
g++ -O3 -std=c++17 -pthread -I/usr/include/xrt "$root/host/window_host.cpp" -lxrt_coreutil -o "$root/bin/window_host_aie"
g++ -O3 -std=c++17 -pthread -I/usr/include/xrt -DWINDOW_PURE_PL "$root/host/window_host.cpp" -lxrt_coreutil -o "$root/bin/window_host_pl"
data=$(python3 "$root/full_board.py" data-path)
"$root/bin/window_parser" --check-data "$data"
python3 "$root/window_board.py" record-build
echo 'BUILD_READY_WINDOW_AND_PURE_PL: self-tests/packing only; no hardware execution, boot write or reboot.'
