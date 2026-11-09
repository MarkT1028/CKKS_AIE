#!/bin/sh
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$root"
python3 -c 'import ga3_board; ga3_board.board()'
python3 ga3_board.py code-check
mkdir -p bin
g++ -O3 -std=c++17 -pthread -Icommon tests/memory_selftest.cpp -o bin/memory_selftest
bin/memory_selftest
g++ -O3 -std=c++17 -pthread frozen_compactio/tests/compact_tool.cpp -ldl -o bin/compact_tool
g++ -O3 -std=c++17 -pthread -DCKKSMAC_PARSER_ONLY host/ga3_host.cpp -ldl -o bin/ga3_parser
data=$(python3 -c 'import ga3_board; print(ga3_board.data())')
bin/ga3_parser --validate "$data"
for name in baseline candidate; do
    source=host/ga3_host.cpp
    if test "$name" = baseline;then source=frozen_compactio/host/ga3_host.cpp;fi
    g++ -O3 -std=c++17 -pthread -DGA3_PACKED_PROFILE=1 -I/usr/include/xrt "$source" -lxrt_coreutil -ldl -o "bin/ga3_host_aie_$name"
    g++ -O3 -std=c++17 -pthread -DGA3_PACKED_PROFILE=1 -I/usr/include/xrt -DWINDOW_PURE_PL -DWINDOW_NATIVE_PL "$source" -lxrt_coreutil -ldl -o "bin/ga3_host_native_$name"
    g++ -O3 -std=c++17 -pthread -DGA3_PACKED_PROFILE=1 -I/usr/include/xrt -DWINDOW_PURE_PL -DWINDOW_NATIVE_PL -include "variants/v32_native_lazy8_2_pipe/host/identity_override_$name.hpp" "$source" -lxrt_coreutil -ldl -o "bin/ga3_host_lazy8_$name"
done
python3 ga3_board.py record-build
bin/ga3_host_aie_candidate --crypto-check
echo 'BUILD_READY_PIPELINE: exact compactio baseline + runtime tuning candidate; no PL/AIE execution.'
