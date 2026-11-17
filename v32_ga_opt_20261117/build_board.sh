#!/bin/sh
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
root=$PWD
base=$root/../v32_ga3_splitbo_20261109
finish=$root/../v32_ga3_finishopt_20261110
live=$root/../v32_ga_live_20261111
layer=${1:-all}
case $layer in ga0|ga3|resident|all) ;; *) echo "expected ga0, ga3, resident or all" >&2; exit 2;; esac
sha256sum -c SHA256SUMS_PACKAGE
sha256sum -c DEPENDENCY_MANIFESTS
for dependency in "$base" "$finish" "$root/../v32_ga0_full_20261114" "$root/../v32_ga_resident_20261114"; do
    (cd "$dependency" && sha256sum --quiet -c SHA256SUMS_PACKAGE)
done

compile() (
    cd "$1"
    source=$2
    binary=$3
    mkdir -p bin
    build=$(mktemp -d bin/.build.XXXXXX)
    trap 'rm -f -- "$build/$binary" "$build/BUILD_SHA256"; rmdir -- "$build"' EXIT
    g++ -O3 -std=c++17 -pthread -I"$base" -I"$base/common" -I/usr/include/xrt \
        -I"$live" -I"$finish" \
        -include "$base/variants/v32_native_splitbo_2_pipe/host/identity_override_candidate.hpp" \
        "$source" -lxrt_coreutil -ldl -o "$build/$binary"
    "$build/$binary" --crypto-check
    digest=$(sha256sum "$build/$binary")
    printf '%s  bin/%s\n' "${digest%% *}" "$binary" > "$build/BUILD_SHA256"
    mv -f -- "$build/$binary" "bin/$binary"
    mv -f -- "$build/BUILD_SHA256" bin/BUILD_SHA256
)

if [ "$layer" = all ] || [ "$layer" = ga0 ]; then
    python3 -B ga0/run_board.py check
    compile ga0 runner.cpp ga0_full
fi
if [ "$layer" = all ] || [ "$layer" = ga3 ]; then
    python3 -B ga3/finish_board.py code-check
    compile ga3 host/candidate.cpp finish_host
    python3 -B ga3/finish_board.py record-build
fi
if [ "$layer" = all ] || [ "$layer" = resident ]; then
    python3 -B resident/run_board.py check
    compile resident runner.cpp ga_resident
fi
echo "BUILD_READY_GA_OPT $layer"
