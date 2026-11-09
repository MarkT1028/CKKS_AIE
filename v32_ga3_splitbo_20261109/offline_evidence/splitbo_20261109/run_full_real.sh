#!/bin/bash
set -euo pipefail
r=/mnt/e/v32_gpu/v32_gpu/integration/ga3_splitbo_20261109
export V32_GA3_CACHE=/mnt/e/v32_gpu/v32_gpu/integration/ga3_pipeline_20261109/build/real_cache
export V32_GA3_PREFETCH=1 V32_GA3_READ_MIB=16
"$r/build/model_candidate" unused /mnt/d/CodexBuilds/v32_ga3_20261104/public_data_v2 "$r/build/full_real_model" stream 1 0 descending 0 > "$r/build/full_real_model.txt" 2>&1
echo PASS_FULL_REAL_1024_WINDOWS_SOFTWARE_TRANSPORT_AND_SHA256_ONLY
