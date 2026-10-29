#!/bin/sh
# Shared checks. Sourcing this file performs no mutation or reset.
perf2_stock=e73f7a483fea0db0e8398f7f8290ff914428ec4cf2cb632b3d86277218371afd
perf2_legacy=c12b4f6cc3de7af24aad06862c2fc88c1b594d01cca496fdd88afbb9cafa89ac
perf2_sd=/run/media/mmcblk0p1
perf2_flag=/run/ckks-perf2-altboot.once
perf2_fail() { echo "FAIL: $*" >&2;exit 1; }
perf2_digest() { sha256sum "$1" | awk '{print $1}'; }
perf2_hash_check() {
  test -f "$1" && test ! -L "$1" || perf2_fail "expected a regular file: $1"
  test "$(perf2_digest "$1")" = "$2" || perf2_fail "SHA256 mismatch: $1"
}
perf2_board_check() {
  test "$(id -u)" = 0 || perf2_fail 'run as root on the VEK280'
  test "$(uname -m)" = aarch64 || perf2_fail 'expected the ARM board, not the PC'
  test -r /sys/firmware/devicetree/base/model || perf2_fail 'device tree missing'
  tr '\000' '\n' < /sys/firmware/devicetree/base/model | grep -qi vek280 || perf2_fail 'expected VEK280'
  awk -v sd="$perf2_sd" '$1=="/dev/mmcblk0p1" && $2==sd && $3=="vfat" && $4 ~ /(^|,)rw(,|$)/ {found=1} END {exit !found}' /proc/mounts || perf2_fail 'expected mounted writable SD FAT boot partition'
  perf2_hash_check "$perf2_sd/BOOT.BIN" "$perf2_stock"
  perf2_hash_check "$perf2_sd/boot0002.bin" "$perf2_stock"
  perf2_hash_check "$perf2_sd/Image" 79359c3f0af65cef3dbabab725b156a4b7b1925f781ab42f2f997be70f6dc86c
  perf2_hash_check "$perf2_sd/boot.scr" ac5f09919439a3a94cf9729ac070d26f6e637acae91796f74f6416d3c10e748e
  for perf2_override in system.dtb uEnv.txt image.ub;do
    test ! -e "$perf2_sd/$perf2_override" && test ! -L "$perf2_sd/$perf2_override" || perf2_fail "boot override exists: $perf2_override"
  done
}
perf2_variant() {
  case "$1" in
    legacy)
      perf2_candidate="$perf2_sd/ckks_saved_SLOT1_c12b4f6cc3de7af2.bin"
      perf2_candidate_sha=$perf2_legacy
      perf2_uuid=1b664c9b428c5972904d75ffc08ea5df ;;
    baseline_1|sink_1|raw_1_pipe|raw_2_shared|raw_2_full|raw_2_pipe|diag_1_pipe|diag_2_pipe|v32_diag_2_pipe|v32_core_2_pipe)
      perf2_candidate="$perf2_root/variants/$1/boot0001.bin"
      perf2_candidate_sha=$(cat "$perf2_root/variants/$1/EXPECTED_BOOT_SHA256")
      perf2_uuid=$(cat "$perf2_root/variants/$1/EXPECTED_BOOT_UUID") ;;
    *) perf2_fail 'unknown variant' ;;
  esac
}
perf2_known_slot() {
  test -f "$perf2_sd/boot0001.bin" && test ! -L "$perf2_sd/boot0001.bin" || perf2_fail 'slot 1 missing or not regular'
  perf2_previous_sha=$(perf2_digest "$perf2_sd/boot0001.bin")
  perf2_known=no
  if test "$perf2_previous_sha" = "$perf2_legacy";then perf2_known=yes;fi
  for perf2_hashfile in "$perf2_root"/variants/*/EXPECTED_BOOT_SHA256;do
    if test -f "$perf2_hashfile" && test "$perf2_previous_sha" = "$(cat "$perf2_hashfile")";then perf2_known=yes;fi
  done
  test "$perf2_known" = yes || perf2_fail 'slot 1 differs from the observed legacy image and every prepared candidate'
}
# Filesystem-only operation, factored for tests with isolated temporary files.
# The production entry point separately verifies the real board/mount/snapshots.
perf2_stage_files() (
  set -eu
  perf2_dir=$1;perf2_source=$2;perf2_before=$3;perf2_after=$4
  perf2_hash_check "$perf2_source" "$perf2_after"
  perf2_hash_check "$perf2_dir/boot0001.bin" "$perf2_before"
  if test "$perf2_before" = "$perf2_after";then echo 'SLOT_ALREADY_MATCHES';exit 0;fi
  perf2_prefix=$(printf '%s' "$perf2_before" | cut -c1-16)
  perf2_backup="$perf2_dir/ckks_saved_SLOT1_$perf2_prefix.bin"
  if test -e "$perf2_backup" || test -L "$perf2_backup";then perf2_hash_check "$perf2_backup" "$perf2_before";fi
  perf2_tmp=
  trap 'test -z "$perf2_tmp" || rm -f -- "$perf2_tmp"' EXIT HUP INT TERM
  if test ! -e "$perf2_backup";then
    perf2_tmp=$(mktemp "$perf2_dir/.ckks-backup-XXXXXXXX")
    cp -- "$perf2_dir/boot0001.bin" "$perf2_tmp"
    perf2_hash_check "$perf2_tmp" "$perf2_before"
    sync
    mv -- "$perf2_tmp" "$perf2_backup";perf2_tmp=
  fi
  perf2_tmp=$(mktemp "$perf2_dir/.ckks-stage-XXXXXXXX")
  cp -- "$perf2_source" "$perf2_tmp"
  perf2_hash_check "$perf2_tmp" "$perf2_after"
  perf2_hash_check "$perf2_dir/boot0001.bin" "$perf2_before"
  sync
  mv -f -- "$perf2_tmp" "$perf2_dir/boot0001.bin";perf2_tmp=
  sync
  perf2_hash_check "$perf2_dir/boot0001.bin" "$perf2_after"
  perf2_hash_check "$perf2_backup" "$perf2_before"
  echo "BACKUP=$perf2_backup"
)
