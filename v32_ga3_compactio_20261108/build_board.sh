#!/bin/sh
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$root"
python3 -c 'import ga3_board; ga3_board.board()'
python3 ga3_board.py code-check
mkdir -p bin
g++ -O3 -std=c++17 -pthread -Icommon tests/memory_selftest.cpp -o bin/memory_selftest
bin/memory_selftest
g++ -O3 -std=c++17 -pthread tests/compact_tool.cpp -ldl -o bin/compact_tool
g++ -O3 -std=c++17 -pthread -DCKKSMAC_PARSER_ONLY host/ga3_host.cpp -ldl -o bin/ga3_parser
data=$(python3 -c 'import ga3_board; print(ga3_board.data())')
bin/ga3_parser --validate "$data"
for definition in 'sha256 0' 'packed 1'; do
    set -- $definition
    name=$1
    number=$2
    g++ -O3 -std=c++17 -pthread -DGA3_PACKED_PROFILE="$number" -I/usr/include/xrt host/ga3_host.cpp -lxrt_coreutil -ldl -o "bin/ga3_host_aie_$name"
    g++ -O3 -std=c++17 -pthread -DGA3_PACKED_PROFILE="$number" -I/usr/include/xrt -DWINDOW_PURE_PL -DWINDOW_NATIVE_PL host/ga3_host.cpp -lxrt_coreutil -ldl -o "bin/ga3_host_native_$name"
done
python3 ga3_board.py record-build
bin/ga3_host_aie_sha256 --crypto-check
echo 'BUILD_READY_COMPACTIO: CPU tools + 2 profiles x 2 backends; firmware unchanged, no PL/AIE execution.'
