#!/bin/sh
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$root"
python3 -c 'import ga3_board; ga3_board.board()'
python3 ga3_board.py code-check
mkdir -p bin
g++ -O3 -std=c++17 -pthread -Icommon tests/memory_selftest.cpp -o bin/memory_selftest
bin/memory_selftest
g++ -O3 -std=c++17 -pthread -DCKKSMAC_PARSER_ONLY host/ga3_host.cpp -ldl -o bin/ga3_parser
data=$(python3 -c 'import ga3_board; print(ga3_board.data())')
bin/ga3_parser --validate "$data"
for definition in 'legacy 0' 'sequential 1' 'sha256 2'; do
    set -- $definition
    name=$1
    number=$2
    g++ -O3 -std=c++17 -pthread -DGA3_IO_PROFILE="$number" -DGA3_OPT_PROFILE=2 -I/usr/include/xrt host/ga3_host.cpp -lxrt_coreutil -ldl -o "bin/ga3_host_aie_$name"
    g++ -O3 -std=c++17 -pthread -DGA3_IO_PROFILE="$number" -DGA3_OPT_PROFILE=2 -I/usr/include/xrt -DWINDOW_PURE_PL -DWINDOW_NATIVE_PL host/ga3_host.cpp -lxrt_coreutil -ldl -o "bin/ga3_host_native_$name"
done
python3 ga3_board.py record-build
python3 probe_crypto.py
echo 'BUILD_READY_GA3_IOOPT: 3 profiles x 2 backends; no PL/AIE run, boot write or reboot.'
