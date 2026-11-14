#!/bin/sh
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
python3 -B run_board.py check
base=../v32_ga3_splitbo_20261109
mkdir -p bin
g++ -O3 -std=c++17 -pthread -I"$base" -I"$base/common" -I/usr/include/xrt \
    -I../v32_ga_live_20261111 -I../v32_ga3_finishopt_20261110 \
    -include "$base/variants/v32_native_splitbo_2_pipe/host/identity_override_candidate.hpp" \
    runner.cpp -lxrt_coreutil -ldl -o bin/ga0_full.tmp
bin/ga0_full.tmp --crypto-check
mv -- bin/ga0_full.tmp bin/ga0_full
sha256sum bin/ga0_full > bin/BUILD_SHA256
echo BUILD_READY_GA0_FULL
