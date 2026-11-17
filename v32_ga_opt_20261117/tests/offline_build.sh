#!/bin/bash
set -euo pipefail
cd "$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
package=$PWD
parent=$package/..
project=$parent/..
base=$parent/v32_ga3_splitbo_20261109
live=$parent/v32_ga_live_20261111
finish=$parent/v32_ga3_finishopt_20261110
headers=$project/experiments/ckks_perf2_20261017/host_api_headers
fixture=$parent/v32_ga0_full_20261114/fixture
out=${1:?pass an output directory}
mkdir -p "$out"
echo "OFFLINE_OUT=$out"
flags=(-O3 -std=c++17 -pthread -I"$base" -I"$base/common" -I"$live" -I"$finish")
g++ "${flags[@]}" -DGA_RESIDENT_MODEL ga0/runner.cpp -ldl -o "$out/ga0_model"
g++ "${flags[@]}" -DGA_RESIDENT_MODEL resident/runner.cpp -ldl -o "$out/resident_model"
g++ "${flags[@]}" -DFINISH_MODEL ga3/host/candidate.cpp -ldl -o "$out/finish_model"
echo PASS_GA_X86_MODELS
# The local header snapshot has no generated XRT version header.
# Board binaries are compiled against the installed SDK, with ABI checks enabled.
arm_flags=(-O3 -std=c++17 -pthread -mcpu=cortex-a72 -DDISABLE_ABI_CHECK -I"$base" -I"$base/common" -I"$live" -I"$finish" -I"$headers"
    -include "$base/variants/v32_native_splitbo_2_pipe/host/identity_override_candidate.hpp")
for entry in ga0/runner.cpp resident/runner.cpp ga3/host/candidate.cpp; do
    aarch64-linux-gnu-g++ "${arm_flags[@]}" -c "$entry" -o "$out/${entry%%/*}.o"
done
echo PASS_GA_ARM64_XRT_OBJECTS
g++ -O3 -std=c++17 tests/ntt_contract.cpp -o "$out/ntt_contract"
"$out/ntt_contract" "$fixture/basis.txt" "$fixture/data/p_00_00_00.bin"
