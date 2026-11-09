#!/bin/bash
set -euo pipefail
r=/mnt/e/v32_gpu/v32_gpu/integration/ga3_splitbo_20261109
g++ -O2 -g -std=c++17 -pthread -fsanitize=address,undefined -fno-omit-frame-pointer "$r/test_host.cpp" -o "$r/build/test_host" > "$r/build/test_host_compile.txt" 2>&1
ASAN_OPTIONS=detect_leaks=1 "$r/build/test_host" > "$r/build/test_host.txt" 2>&1
echo PASS_SPLIT_HOST_CACHE_OWNERSHIP_AND_ASAN_UBSAN
