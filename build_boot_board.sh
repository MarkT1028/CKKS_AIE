#!/bin/sh
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
sha256sum -c SHA256SUMS
g++ -std=c++17 -O2 -Wall -Wextra -pthread -I/usr/include/xrt/detail \
    ckks_mac_boot_xrt.cpp -o ckks_mac_boot_xrt -lxrt_coreutil
./ckks_mac_boot_xrt --inspect-xclbin ckks_hw_boot.xclbin
printf '%s\n' 'BUILD_READY: compiled and checked; no hardware was programmed or accessed.'
