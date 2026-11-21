#!/bin/sh
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
root=$PWD
base=$root/../v32_ga3_splitbo_20261109
finish=$root/../v32_ga3_finishopt_20261110
live=$root/../v32_ga_live_20261111
python3 -B run_board.py check

selection=${1:?usage: sh build_board.sh ctpt|splitbo|dual3|tuned}
export V32_GA_IMAGE=$selection
binding=$(python3 -B - <<'PY'
import sys
sys.path.insert(0, 'common')
from ga_all_board import selected_image
label, image = selected_image()
image.check_xclbin()
print(image.variant, image.uuid, 65536 if label == 'dual3' else 0, int(label == 'tuned'))
PY
)
read -r variant uuid ctpt_flag distinct_ctpt <<EOF
$binding
EOF

compile() (
    cd "$1"
    source=$2 binary=$3
    out=bin/$selection
    mkdir -p "$out"
    scratch=$(mktemp -d "$out/.build.XXXXXX")
    trap 'rm -f -- "$scratch/$binary" "$scratch/BUILD_SHA256"; rmdir -- "$scratch"' EXIT
    g++ -O3 -mcpu=cortex-a72 -std=c++17 -pthread -I"$base" -I"$base/common" -I"$finish" -I"$live" -I/usr/include/xrt \
        "-DV32_GA_BUILD_UUID=\"$uuid\"" "-DV32_GA_BUILD_VARIANT=\"$variant\"" "-DV32_GA_CTPT_MODE_FLAG=$ctpt_flag" \
        "-DV32_GA_DISTINCT_CTPT=$distinct_ctpt" \
        -include "$root/common/identity.hpp" "$source" -lxrt_coreutil -ldl -o "$scratch/$binary"
    "$scratch/$binary" --crypto-check
    digest=$(sha256sum "$scratch/$binary")
    package_digest=$(sha256sum "$root/SHA256SUMS_PACKAGE")
    printf '%s  %s\n' "${digest%% *}" "$binary" "${package_digest%% *}" '../../../SHA256SUMS_PACKAGE' \
        > "$scratch/BUILD_SHA256"
    mv -f -- "$scratch/$binary" "$out/$binary"
    mv -f -- "$scratch/BUILD_SHA256" "$out/BUILD_SHA256"
)

if test "$selection" != splitbo; then
    compile ga0 runner.cpp ga0_ctpt
fi
if test "$selection" != ctpt; then
    compile ga3 host/candidate.cpp finish_host
    compile resident runner.cpp ga_resident
    python3 -B ga3/finish_board.py record-build
fi
echo "BUILD_READY_GA_OVERLAP image=$selection"
