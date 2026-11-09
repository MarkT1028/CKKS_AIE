#!/bin/sh
# Stage only; never install over BOOT.BIN, change registers, or reboot.
set -eu
perf2_root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
. "$perf2_root/perf2_boot_common.sh"
perf2_name=${1:?usage: stage_variant_board.sh VARIANT_OR_legacy [--check]}
case "${2-}" in ''|--check) ;;*) perf2_fail 'second argument must be --check or omitted';;esac
perf2_board_check
cd "$perf2_root"
sha256sum -c SHA256SUMS_PACKAGE
perf2_variant "$perf2_name"
perf2_hash_check "$perf2_candidate" "$perf2_candidate_sha"
perf2_known_slot
test ! -e /run/ckks-altboot-srst.once && test ! -e "$perf2_flag" || perf2_fail 'a reboot request is armed; cancel it before changing slot 1'
perf2_needed=$(( ( $(wc -c < "$perf2_sd/boot0001.bin") + $(wc -c < "$perf2_candidate") ) / 1024 + 16384 ))
perf2_available=$(df -Pk "$perf2_sd" | awk 'NR==2 {print $4}')
test "$perf2_available" -gt "$perf2_needed" || perf2_fail 'not enough SD space for backup and atomic staging'
printf 'STAGING_PLAN variant=%s previous_sha=%s target_sha=%s expected_boot_uuid=%s\n' "$perf2_name" "$perf2_previous_sha" "$perf2_candidate_sha" "$perf2_uuid"
if test "${2-}" = --check;then echo 'CHECK_ONLY: no files or registers changed';exit 0;fi
perf2_lock=/run/ckks-perf2-boot.lock
mkdir "$perf2_lock" || perf2_fail 'another switch operation is active'
trap 'rmdir "$perf2_lock"' EXIT HUP INT TERM
# Repeat mutable-state checks after taking the lock.
test ! -e /run/ckks-altboot-srst.once && test ! -e "$perf2_flag" || perf2_fail 'a reboot request is armed'
perf2_stage_files "$perf2_sd" "$perf2_candidate" "$perf2_previous_sha" "$perf2_candidate_sha"
perf2_hash_check "$perf2_sd/BOOT.BIN" "$perf2_stock"
perf2_hash_check "$perf2_sd/boot0002.bin" "$perf2_stock"
mkdir -p "$perf2_root/switch_logs"
perf2_record=$(mktemp "$perf2_root/switch_logs/staged_${perf2_name}_XXXXXXXX.txt")
{ date -u;printf 'variant=%s\nprevious_sha=%s\ncandidate_sha=%s\nexpected_boot_uuid=%s\n' "$perf2_name" "$perf2_previous_sha" "$perf2_candidate_sha" "$perf2_uuid"; } > "$perf2_record"
echo "STAGED_ONLY: slot 1 now matches $perf2_name; BOOT.BIN and slot 2 preserved; no reset occurred"
echo "NEXT: sh prepare_variant_srst.sh $perf2_name"
