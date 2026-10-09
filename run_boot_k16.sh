#!/bin/sh
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
# Use the host and metadata already validated by the passing K1 deployment.
sha256sum -c SHA256SUMS
sha256sum -c SHA256SUMS_K16
test -x ./ckks_mac_boot_xrt || {
  echo 'ERROR: missing compiled boot host; run build_boot_board.sh first.' >&2
  exit 1
}
test ! -e output_k16_boot.bin || {
  echo 'ERROR: output_k16_boot.bin already exists; preserve it before another run.' >&2
  exit 1
}
./ckks_mac_boot_xrt --inspect-xclbin ckks_hw_boot.xclbin
./ckks_mac_boot_xrt ckks_hw_boot.xclbin inputs_k16.bin output_k16_boot.bin 120000
cmp expected_k16_raw.bin output_k16_boot.bin
printf '%s\n' 'PASS K16: all output residues and header match the software reference.'
