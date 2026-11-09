#!/bin/bash
set -euo pipefail
ga3_root=/mnt/e/v32_gpu/v32_gpu/integration/v32_ga3_20261104
ga3_kit=/mnt/e/v32_gpu/v32_gpu/board_packages/v32_ga3_20261104
ga3_headers=/mnt/e/v32_gpu/v32_gpu/experiments/ckks_perf2_20261017/host_api_headers
ga3_testdir=$(mktemp -d "$ga3_root/build/host_tests_XXXXXXXX")
echo "$ga3_testdir" > "$ga3_root/build/latest_host_tests.txt"
python3 "$ga3_root/tests/make_fixture.py" "$ga3_testdir/data_full" 17
python3 "$ga3_root/tests/make_fixture.py" "$ga3_testdir/data_pilot" 53 pilot
g++ -O2 -std=c++17 -pthread -DWINDOW_SOFTWARE_MODEL "$ga3_kit/host/ga3_host.cpp" -o "$ga3_root/build/ga3_model"
g++ -O2 -std=c++17 -pthread -fsyntax-only -DDISABLE_ABI_CHECK -I"$ga3_headers" "$ga3_kit/host/ga3_host.cpp" > "$ga3_root/build/xrt_aie_syntax.log" 2>&1
g++ -O2 -std=c++17 -pthread -fsyntax-only -DDISABLE_ABI_CHECK -DWINDOW_PURE_PL -DWINDOW_NATIVE_PL -I"$ga3_headers" "$ga3_kit/host/ga3_host.cpp" > "$ga3_root/build/xrt_native_syntax.log" 2>&1
"$ga3_root/build/ga3_model" unused "$ga3_testdir/data_full" "$ga3_testdir/model_stream_full" stream 1 0 descending 0 > "$ga3_testdir/model_stream_full.log" 2>&1
"$ga3_root/build/ga3_model" unused "$ga3_testdir/data_pilot" "$ga3_testdir/model_audit_pilot" export 1 0 ascending 0 > "$ga3_testdir/model_audit_pilot.log" 2>&1
"$ga3_root/build/ga3_model" unused "$ga3_testdir/data_pilot" "$ga3_testdir/model_windows_pilot" windows 3 1 descending 0 > "$ga3_testdir/model_windows_pilot.log" 2>&1
g++ -O1 -g -std=c++17 -pthread -DWINDOW_SOFTWARE_MODEL -fsanitize=address,undefined -fno-omit-frame-pointer "$ga3_kit/host/ga3_host.cpp" -o "$ga3_root/build/ga3_asan"
ASAN_OPTIONS=detect_leaks=1 "$ga3_root/build/ga3_asan" unused "$ga3_testdir/data_pilot" "$ga3_testdir/model_asan_smoke" smoke 2 1 descending 2 > "$ga3_testdir/model_asan_smoke.log" 2>&1
python3 "$ga3_root/tests/test_contracts.py" "$ga3_testdir"
echo PASS_GA3_SYNTHETIC_FULL_GRID_SYNTAX_ASAN_UBSAN
