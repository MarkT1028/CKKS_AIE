#!/bin/sh
# Install an inert hook and arm a RAM-only request; this command never resets.
set -eu
perf2_root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
. "$perf2_root/perf2_boot_common.sh"
if test "${1-}" = --cancel;then
  test "$(id -u)" = 0 || perf2_fail 'run as root'
  rm -f -- "$perf2_flag"
  echo 'PERF2_REQUEST_CANCELLED: no reset occurred';exit 0
fi
perf2_name=${1:?usage: prepare_variant_srst.sh VARIANT_OR_legacy [--check]}
case "${2-}" in ''|--check) ;;*) perf2_fail 'second argument must be --check or omitted';;esac
perf2_board_check
cd "$perf2_root"
sha256sum -c SHA256SUMS_PACKAGE
perf2_variant "$perf2_name"
perf2_hash_check "$perf2_sd/boot0001.bin" "$perf2_candidate_sha"
test ! -e /run/ckks-altboot-srst.once || perf2_fail 'legacy reboot hook is armed; cancel the old request first'
test -d /run/systemd/system && test -x /usr/lib/systemd/systemd-shutdown || perf2_fail 'expected systemd shutdown flow'
test -x /usr/sbin/devmem || perf2_fail 'devmem missing'
if awk '$2=="/usr" {found=1} END {exit !found}' /proc/mounts;then perf2_fail 'separate /usr mount is unsupported';fi
perf2_hook=/usr/lib/systemd/system-shutdown/ckks-perf2-srst
if test -e "$perf2_hook" || test -L "$perf2_hook";then
  test -f "$perf2_hook" && test ! -L "$perf2_hook" && cmp -s "$perf2_root/ckks-perf2-srst" "$perf2_hook" || perf2_fail 'a different hook occupies the new hook path'
fi
printf 'ARM_PLAN variant=%s candidate_sha=%s expected_boot_uuid=%s\n' "$perf2_name" "$perf2_candidate_sha" "$perf2_uuid"
if test "${2-}" = --check;then echo 'CHECK_ONLY: no files, request or registers changed';exit 0;fi
perf2_lock=/run/ckks-perf2-boot.lock
mkdir "$perf2_lock" || perf2_fail 'another switch operation is active'
perf2_tmp=
trap 'test -z "$perf2_tmp" || rm -f -- "$perf2_tmp";rmdir "$perf2_lock"' EXIT HUP INT TERM
perf2_hash_check "$perf2_sd/boot0001.bin" "$perf2_candidate_sha"
test ! -e /run/ckks-altboot-srst.once || perf2_fail 'legacy request became armed'
mkdir -p /usr/lib/systemd/system-shutdown
if test ! -e "$perf2_hook";then
  perf2_tmp=$(mktemp /usr/lib/systemd/system-shutdown/.ckks-perf2-XXXXXXXX)
  cp -- "$perf2_root/ckks-perf2-srst" "$perf2_tmp"
  chmod 755 "$perf2_tmp"
  cmp -s "$perf2_root/ckks-perf2-srst" "$perf2_tmp" || perf2_fail 'hook copy mismatch'
  mv -- "$perf2_tmp" "$perf2_hook";perf2_tmp=
fi
perf2_tmp=$(mktemp /run/.ckks-perf2-request-XXXXXXXX)
printf 'CKKS_PERF2_SLOT1\nvariant=%s\ncandidate_sha=%s\nexpected_boot_uuid=%s\n' "$perf2_name" "$perf2_candidate_sha" "$perf2_uuid" > "$perf2_tmp"
chmod 600 "$perf2_tmp"
mv -f -- "$perf2_tmp" "$perf2_flag";perf2_tmp=
sync
echo 'ARMED_ONLY: no reset has occurred; keep the board serial console open'
echo 'NEXT: sync && reboot'
echo 'CANCEL before reboot: sh prepare_variant_srst.sh --cancel'
