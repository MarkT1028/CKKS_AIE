#!/bin/sh
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
[ "$(uname -m)" = aarch64 ] || { echo 'FAIL: compile on VEK280 Linux'; exit 1; }
sha256sum -c SHA256SUMS_DIAG
g++ -std=c++17 -O3 -Wall -Wextra ckks_mac_persistent_xrt.cpp -o ckks_mac_persistent_xrt -lxrt_coreutil -pthread
g++ -std=c++17 -O3 -Wall -Wextra ckks_mac_cpu_bench.cpp -o ckks_mac_cpu_bench
./ckks_mac_persistent_xrt --capabilities
echo 'DIAG_BUILD_READY: compiled only; hardware was not executed.'
