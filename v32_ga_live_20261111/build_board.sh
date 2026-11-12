#!/bin/sh
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
base=../v32_ga3_splitbo_20261109
python3 -B serve_board.py check
mkdir -p bin
g++ -O3 -std=c++17 -pthread -I"$base" -I"$base/common" -I/usr/include/xrt \
    -include "$base/variants/v32_native_splitbo_2_pipe/host/identity_override_candidate.hpp" \
    serve.cpp -lxrt_coreutil -ldl -o bin/ga_server.tmp
mv -- bin/ga_server.tmp bin/ga_server
sha256sum bin/ga_server > bin/BUILD_SHA256
echo BUILD_READY_GA_LIVE
