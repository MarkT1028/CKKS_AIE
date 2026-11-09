#!/bin/bash
set -euo pipefail
r=/mnt/e/v32_gpu/v32_gpu/integration/ga3_splitbo_20261109
k=/mnt/e/v32_gpu/v32_gpu/board_packages/v32_ga3_splitbo_20261109
headers=/mnt/e/v32_gpu/v32_gpu/experiments/ckks_perf2_20261017/host_api_headers
mkdir -p "$r/build"
cat > "$r/build/temporary_split_identity.hpp" <<'EOF'
#pragma once
#include "/mnt/e/v32_gpu/v32_gpu/board_packages/v32_ga3_splitbo_20261109/variants/v32_native_pl_2_pipe/host/variant_config.hpp"
#undef PERF_BOOT_UUID
#undef PERF_VARIANT_ID
#define PERF_BOOT_UUID "00000000000000000000000000000001"
#define PERF_VARIANT_ID "v32_native_splitbo_2_pipe"
EOF
for backend in native split; do
 flags=(-DWINDOW_PURE_PL -DWINDOW_NATIVE_PL)
 if [ "$backend" = split ];then flags+=(-DWINDOW_SPLIT_PL -include "$r/build/temporary_split_identity.hpp");fi
 for cc in g++ aarch64-linux-gnu-g++;do
  "$cc" -O2 -std=c++17 -pthread -DGA3_PACKED_PROFILE=1 -DDISABLE_ABI_CHECK -I"$headers" "${flags[@]}" -fsyntax-only "$k/host/ga3_host.cpp" > "$r/build/${backend}_${cc}.txt" 2>&1
 done
done
g++ -O3 -std=c++17 -pthread -DGA3_PACKED_PROFILE=1 -DWINDOW_SOFTWARE_MODEL "$k/host/ga3_host.cpp" -ldl -o "$r/build/model_candidate" > "$r/build/model_compile.txt" 2>&1
echo PASS_X86_ARM64_XRT_SPLIT_AND_MODEL_COMPILE
