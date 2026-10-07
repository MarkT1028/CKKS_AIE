#!/bin/sh
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
sha256sum -c SHA256SUMS
./ckks_mac_xrt_runtime --inspect-xclbin ckks_hw_runtime.xclbin
./ckks_mac_xrt_runtime ckks_hw_runtime.xclbin inputs.bin output_k01_runtime.bin 120000
cmp expected_raw.bin output_k01_runtime.bin
printf '%s\n' 'PASS K1: all output residues and the output header match the software reference.'
