#!/bin/sh
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
variant=${1:?usage: build_perf_board.sh VARIANT}
case "$variant" in baseline_1|sink_1|raw_1_pipe|raw_2_shared|raw_2_full|raw_2_pipe|diag_1_pipe|diag_2_pipe) ;; *) echo 'invalid variant' >&2;exit 2;;esac
test "$(uname -m)" = aarch64 || { echo 'Build this ARM host on the VEK280 Linux board.' >&2;exit 2; }
test -r /sys/firmware/devicetree/base/model
tr '\000' '\n' < /sys/firmware/devicetree/base/model | grep -qi vek280 || { echo 'Expected VEK280 device tree.' >&2;exit 2; }
cd "$root"
sha256sum -c SHA256SUMS_PACKAGE
src="$root/variants/$variant/host"
test -s "$src/variant_config.hpp"
test -s "$root/variants/$variant/ckks_hw_boot.xclbin"
mkdir -p "$root/bin"
temp="$root/bin/perf_host_$variant.tmp.$$"
trap 'rm -f -- "$temp"' EXIT HUP INT TERM
g++ -std=c++17 -O3 -Wall -Wextra -pthread "$src/perf_host.cpp" -lxrt_coreutil -o "$temp"
mv -- "$temp" "$root/bin/perf_host_$variant"
sha256sum "$root/bin/perf_host_$variant" > "$root/bin/perf_host_$variant.sha256"
sha256sum "$src/perf_host.cpp" "$src/timed_base.hpp" "$src/expected_reader.hpp" "$src/variant_config.hpp" > "$root/bin/perf_host_$variant.sources.sha256"
{
  date -u
  uname -a
  g++ --version
  printf 'COMPILE_FLAGS=-std=c++17 -O3 -Wall -Wextra -pthread; XRT ABI checks enabled\n'
  cat "$root/bin/perf_host_$variant.sources.sha256"
  if command -v ldd >/dev/null 2>&1;then ldd "$root/bin/perf_host_$variant";fi
} > "$root/bin/perf_host_$variant.build.txt"
echo "HOST_BUILD_READY=$root/bin/perf_host_$variant"
echo 'Compilation only; no hardware execution or boot-image installation.'
