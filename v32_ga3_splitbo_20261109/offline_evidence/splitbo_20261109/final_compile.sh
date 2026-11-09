#!/bin/bash
set -euo pipefail
r=/mnt/e/v32_gpu/v32_gpu/integration/ga3_splitbo_20261109
k=/mnt/e/v32_gpu/v32_gpu/board_packages/v32_ga3_splitbo_20261109
headers=/mnt/e/v32_gpu/v32_gpu/experiments/ckks_perf2_20261017/host_api_headers
for cc in g++ aarch64-linux-gnu-g++;do
 "$cc" -O2 -std=c++17 -pthread -DGA3_PACKED_PROFILE=1 -DDISABLE_ABI_CHECK -I"$headers" -DWINDOW_PURE_PL -DWINDOW_NATIVE_PL -DWINDOW_SPLIT_PL -include "$k/variants/v32_native_splitbo_2_pipe/host/identity_override_candidate.hpp" -fsyntax-only "$k/host/ga3_host.cpp" > "$r/build/final_${cc}.txt" 2>&1
done
g++ -O2 -std=c++17 -pthread -DGA3_PACKED_PROFILE=1 -DDISABLE_ABI_CHECK -I"$headers" -DWINDOW_PURE_PL -DWINDOW_NATIVE_PL -DWINDOW_SPLIT_PL -include "$k/variants/v32_native_splitbo_2_pipe/host/identity_override_candidate.hpp" -c "$k/host/ga3_host.cpp" -o "$r/build/split_candidate.o" > "$r/build/final_object.txt" 2>&1
nm -C "$r/build/split_candidate.o" > "$r/build/split_symbols.txt"
python3 -c 'from pathlib import Path; import sys; assert "xrt::graph::" not in Path(sys.argv[1]).read_text()' "$r/build/split_symbols.txt"
echo PASS_FINAL_IMAGE_XRT_ARM64_AND_NO_GRAPH_SYMBOLS
