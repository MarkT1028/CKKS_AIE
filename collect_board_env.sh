#!/bin/sh
# Read-only inventory. No devmem writes, firmware reload, reset or frequency change.
set -u
printf 'UTC='; date -u '+%Y-%m-%dT%H:%M:%SZ'
uname -a
cat /etc/os-release 2>/dev/null || true
g++ --version 2>/dev/null | head -n 1
printf '\nBOOT_MARKER='; tr '\000' '\n' < /sys/firmware/devicetree/base/chosen/ckks,boot-xclbin-uuid 2>/dev/null || true
printf '\nMEMORY\n'; grep -E 'MemTotal|MemAvailable|CmaTotal|CmaFree' /proc/meminfo
printf '\nLOAD\n'; cat /proc/loadavg
printf '\nCPU_FREQUENCY_SYSFS\n'
for p in /sys/devices/system/cpu/cpufreq/policy*/scaling_cur_freq /sys/devices/system/cpu/cpufreq/policy*/scaling_governor; do
    [ ! -r "$p" ] || { printf '%s=' "$p"; cat "$p"; }
done
printf '\nAIE_FREQUENCY_SYSFS_READ_ONLY\n'
for p in /sys/class/aie/*/freq /sys/bus/platform/devices/*aie*/freq /sys/bus/platform/devices/*aie*/*/freq; do
    [ ! -r "$p" ] || { printf '%s=' "$p"; cat "$p"; }
done
printf '\nXRT_LIBRARIES_AND_PROFILE_PLUGINS\n'
for p in /usr/lib /usr/lib64 /opt/xilinx/xrt/lib; do
    [ ! -d "$p" ] || find "$p" -maxdepth 3 \( -name '*xrt*' -o -name '*aie*profile*' \) -type f -print 2>/dev/null
done
printf '\nXRT_TOOLS\n'
for tool in xrt-smi xbutil xclbinutil; do
    command -v "$tool" 2>/dev/null || true
done
printf '\nRECENT_AIE_KERNEL_MESSAGES\n'
dmesg 2>/dev/null | grep -Ei 'aie|zocl|frequency|freq_divider|cma' | tail -n 50 || true
printf '\nNOTE: compile-time metadata frequency is not a measured runtime frequency.\n'
