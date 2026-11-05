#!/bin/sh
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$root"
python3 -c 'import ga3_board; ga3_board.board()'
python3 ga3_board.py code-check
mkdir -p bin
g++ -O3 -std=c++17 -pthread -DCKKSMAC_PARSER_ONLY host/ga3_host.cpp -o bin/ga3_parser
data=$(python3 -c 'import ga3_board; print(ga3_board.data())')
bin/ga3_parser --validate "$data"
g++ -O3 -std=c++17 -pthread -I/usr/include/xrt host/ga3_host.cpp -lxrt_coreutil -o bin/ga3_host_aie
g++ -O3 -std=c++17 -pthread -I/usr/include/xrt -DWINDOW_PURE_PL -DWINDOW_NATIVE_PL host/ga3_host.cpp -lxrt_coreutil -o bin/ga3_host_native
python3 ga3_board.py record-build
echo 'BUILD_READY_GA3: no PL/AIE execution, boot write or reboot.'
