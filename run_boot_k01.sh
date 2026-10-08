#!/bin/sh
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
sha256sum -c SHA256SUMS
./ckks_mac_boot_xrt --inspect-xclbin ckks_hw_boot.xclbin
./ckks_mac_boot_xrt ckks_hw_boot.xclbin inputs.bin output_k01_boot.bin 120000
cmp expected_raw.bin output_k01_boot.bin
printf '%s\n' 'PASS K1: all output residues and header match the software reference.'
