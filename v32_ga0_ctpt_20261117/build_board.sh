#!/bin/sh
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
python3 -B run_board.py check
base=../v32_ga3_splitbo_20261109
live=../v32_ga_live_20261111
mkdir -p bin
build=$(mktemp -d bin/.build.XXXXXX)
trap 'rm -f -- "$build/ga0_ctpt" "$build/BUILD_SHA256"; rmdir -- "$build"' EXIT
g++ -O3 -std=c++17 -pthread -I"$base" -I"$base/common" -I"$live" -I/usr/include/xrt \
    -include host/identity.hpp host/runner.cpp -lxrt_coreutil -ldl -o "$build/ga0_ctpt"
"$build/ga0_ctpt" --crypto-check
digest=$(sha256sum "$build/ga0_ctpt")
printf '%s  bin/ga0_ctpt\n' "${digest%% *}" > "$build/BUILD_SHA256"
mv -f -- "$build/ga0_ctpt" bin/ga0_ctpt
mv -f -- "$build/BUILD_SHA256" bin/BUILD_SHA256
echo BUILD_READY_GA0_CTPT_COMPACT
