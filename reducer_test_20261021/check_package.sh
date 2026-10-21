#!/bin/sh
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$root"
sha256sum -c SHA256SUMS_PACKAGE
for variant in raw_2_full raw_2_pipe;do
  expected_sha=$(cat "variants/$variant/EXPECTED_BOOT_SHA256")
  actual_sha=$(sha256sum "variants/$variant/boot0001.bin" | awk '{print $1}')
  test "$expected_sha" = "$actual_sha" || { echo 'BOOT_SHA_MISMATCH' >&2;exit 2; }
  expected_uuid=$(cat "variants/$variant/EXPECTED_BOOT_UUID")
  test "${#expected_uuid}" -eq 32 || exit 2
  grep -Fqx "#define PERF_BOOT_UUID \"$expected_uuid\"" "variants/$variant/host/variant_config.hpp"
  grep -Fqx '#define PERF_CORES 2' "variants/$variant/host/variant_config.hpp"
  grep -Fqx '#define PERF_SPLIT 1' "variants/$variant/host/variant_config.hpp"
done
for name in perf_host.cpp timed_base.hpp expected_reader.hpp;do
  cmp -s "variants/raw_2_full/host/$name" "variants/raw_2_pipe/host/$name" || { echo "HOST_SOURCE_MISMATCH: $name" >&2;exit 2; }
done
echo 'PACKAGE_READY: two AIE cores; raw_2_pipe candidate, raw_2_full reference; no board execution performed.'
