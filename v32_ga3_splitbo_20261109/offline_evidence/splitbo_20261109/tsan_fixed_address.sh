#!/bin/bash
set -euo pipefail
r=/mnt/e/v32_gpu/v32_gpu/integration/ga3_splitbo_20261109
TSAN_OPTIONS=halt_on_error=1 setarch x86_64 -R "$r/build/test_host_tsan_nopie" > "$r/build/test_host_tsan_fixed.txt" 2>&1
echo PASS_SPLIT_BACKEND_THREAD_SANITIZER_FIXED_PROCESS_LAYOUT
