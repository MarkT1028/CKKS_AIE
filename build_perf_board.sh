#!/bin/sh
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
[ "$(uname -m)" = aarch64 ] || { echo 'FAIL: build on the VEK280 Linux board'; exit 1; }
sha256sum -c SHA256SUMS_PERF
g++ -std=c++17 -O3 -Wall -Wextra ckks_mac_timed_xrt.cpp -o ckks_mac_timed_xrt -lxrt_coreutil -pthread
g++ -std=c++17 -O3 -Wall -Wextra ckks_mac_cpu_bench.cpp -o ckks_mac_cpu_bench
./ckks_mac_timed_xrt --inspect-xclbin ckks_hw_boot.xclbin
echo 'PERF_BUILD_READY: compiled and checked; hardware has not been executed.'
