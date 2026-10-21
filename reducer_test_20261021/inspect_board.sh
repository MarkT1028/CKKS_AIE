#!/bin/sh
# Read-only inventory for matching a candidate to the actual board state.
set -eu
printf '=== SYSTEM ===\n'
uname -a
date -u
for p in /sys/firmware/devicetree/base/model /sys/firmware/devicetree/base/chosen/ckks,boot-xclbin-uuid;do
  if test -r "$p";then printf '%s: ' "$p";tr '\000' '\n' < "$p";fi
done
printf '=== NETWORK ===\n'
if command -v ip >/dev/null 2>&1;then ip -br address;ip route;fi
printf '=== STORAGE ===\n'
if command -v lsblk >/dev/null 2>&1;then lsblk -o NAME,SIZE,FSTYPE,MOUNTPOINTS;fi
cat /proc/mounts
printf '=== BOOT FILES (READ ONLY) ===\n'
for d in /run/media/mmcblk0p1 /boot;do
  if test -d "$d";then
    ls -la "$d"
    for f in BOOT.BIN boot0001.bin boot0002.bin Image boot.scr system.dtb uEnv.txt image.ub;do
      if test -f "$d/$f";then sha256sum "$d/$f";fi
    done
  fi
done
printf '=== MEMORY / LOAD ===\n'
sed -n '/^MemTotal:/p;/^MemAvailable:/p;/^CmaTotal:/p;/^CmaFree:/p' /proc/meminfo
cat /proc/loadavg
printf 'INSPECTION_ONLY: no file, register, boot selector or hardware state was changed.\n'
