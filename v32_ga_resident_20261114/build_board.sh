#!/bin/sh
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
base=../v32_ga3_splitbo_20261109
python3 -B run_board.py check
mkdir -p bin
build_dir=$(mktemp -d bin/.build.XXXXXX)
trap 'rm -f -- "$build_dir/ga_resident" "$build_dir/BUILD_SHA256"; rmdir -- "$build_dir"' EXIT
g++ -O3 -std=c++17 -pthread -I"$base" -I"$base/common" -I/usr/include/xrt \
    -I../v32_ga_live_20261111 -I../v32_ga3_finishopt_20261110 \
    -include "$base/variants/v32_native_splitbo_2_pipe/host/identity_override_candidate.hpp" \
    runner.cpp -lxrt_coreutil -ldl -o "$build_dir/ga_resident"
"$build_dir/ga_resident" --crypto-check
digest=$(sha256sum "$build_dir/ga_resident")
printf '%s  bin/ga_resident\n' "${digest%% *}" > "$build_dir/BUILD_SHA256"
mv -- "$build_dir/ga_resident" bin/ga_resident
mv -- "$build_dir/BUILD_SHA256" bin/BUILD_SHA256
echo BUILD_READY_GA_RESIDENT
