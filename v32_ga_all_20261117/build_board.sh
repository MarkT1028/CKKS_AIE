#!/bin/sh
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
root=$PWD
base=$root/../v32_ga3_splitbo_20261109
finish=$root/../v32_ga3_finishopt_20261110
live=$root/../v32_ga_live_20261111
python3 -B run_board.py check

compile() (
    cd "$1"
    source=$2 binary=$3
    mkdir -p bin
    scratch=$(mktemp -d bin/.build.XXXXXX)
    trap 'rm -f -- "$scratch/$binary" "$scratch/BUILD_SHA256"; rmdir -- "$scratch"' EXIT
    g++ -O3 -std=c++17 -pthread -I"$base" -I"$base/common" -I"$finish" -I"$live" -I/usr/include/xrt \
        -include "$root/common/identity.hpp" "$source" -lxrt_coreutil -ldl -o "$scratch/$binary"
    "$scratch/$binary" --crypto-check
    digest=$(sha256sum "$scratch/$binary")
    printf '%s  bin/%s\n' "${digest%% *}" "$binary" > "$scratch/BUILD_SHA256"
    mv -f -- "$scratch/$binary" "bin/$binary"
    mv -f -- "$scratch/BUILD_SHA256" bin/BUILD_SHA256
)

compile ga0 runner.cpp ga0_ctpt
compile ga3 host/candidate.cpp finish_host
compile resident runner.cpp ga_resident
python3 -B ga3/finish_board.py record-build
echo BUILD_READY_GA_ALL
