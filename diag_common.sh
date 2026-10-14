#!/bin/sh
diag_require() {
    [ "$(uname -m)" = aarch64 ] || { echo 'FAIL: run on VEK280 Linux'; exit 1; }
    sha256sum -c SHA256SUMS_DIAG
    base=$(CDPATH= cd -- "${CKKS_BASE:-..}" && pwd)
    for file in ckks_hw_boot.xclbin inputs.bin expected_raw.bin inputs_k16.bin expected_k16_raw.bin; do
        [ -r "$base/$file" ] || { echo "FAIL: missing $base/$file; set CKKS_BASE to the existing AIE folder"; exit 1; }
    done
    [ -x ./ckks_mac_persistent_xrt ] || { echo 'FAIL: run sh build_diag_board.sh first'; exit 1; }
    (cd "$base" && sha256sum -c "$diag_dir/SHA256SUMS_FIXTURES")
    ./ckks_mac_persistent_xrt --inspect-xclbin "$base/ckks_hw_boot.xclbin"
    ./ckks_mac_persistent_xrt --inspect-case "$base/inputs.bin" "$base/expected_raw.bin"
    ./ckks_mac_persistent_xrt --inspect-case "$base/inputs_k16.bin" "$base/expected_k16_raw.bin"
}
diag_case() {
    if [ "$k" = 1 ]; then input="$base/inputs.bin"; expected="$base/expected_raw.bin"
    else input="$base/inputs_k16.bin"; expected="$base/expected_k16_raw.bin"; fi
}
