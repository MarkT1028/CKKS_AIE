#!/bin/sh
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
sha256sum -c SHA256SUMS
g++ -std=c++17 -O2 -Wall -Wextra -pthread -I/usr/include/xrt/detail \
    ckks_mac_xrt.cpp -o ckks_mac_xrt_runtime -lxrt_coreutil
./ckks_mac_xrt_runtime --inspect-xclbin ckks_hw_runtime.xclbin
printf '%s\n' 'BUILD_READY: host compiled and xclbin checked; no hardware was programmed.'
