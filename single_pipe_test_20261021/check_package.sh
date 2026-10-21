#!/bin/sh
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$root"
sha256sum -c SHA256SUMS_PACKAGE
for variant in baseline_1 raw_1_pipe;do
  expected_sha=$(cat "variants/$variant/EXPECTED_BOOT_SHA256")
  actual_sha=$(sha256sum "variants/$variant/boot0001.bin" | awk '{print $1}')
  test "$expected_sha" = "$actual_sha" || { echo 'BOOT_SHA_MISMATCH' >&2;exit 2; }
  expected_uuid=$(cat "variants/$variant/EXPECTED_BOOT_UUID")
  test "${#expected_uuid}" -eq 32 || exit 2
  grep -Fqx "#define PERF_BOOT_UUID \"$expected_uuid\"" "variants/$variant/host/variant_config.hpp"
  for setting in 'PERF_CORES 1' 'PERF_SPLIT 0' 'PERF_SHARED 0' 'PERF_SINK 0' 'PERF_COMPACT 0';do
    grep -Fqx "#define $setting" "variants/$variant/host/variant_config.hpp"
  done
done
for name in perf_host.cpp timed_base.hpp expected_reader.hpp;do
  cmp -s "variants/baseline_1/host/$name" "variants/raw_1_pipe/host/$name" || { echo "HOST_SOURCE_MISMATCH: $name" >&2;exit 2; }
done
echo 'PACKAGE_READY: one AIE core per variant; raw_1_pipe candidate, baseline_1 reference.'
