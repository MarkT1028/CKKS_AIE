#!/bin/sh
# Stage a one-shot SRST after systemd has stopped services and made storage safe.
# Addresses/mask match AMD 2025.2 xilplmi: PMC_MULTI_BOOT, CRP_RST_PS.PMC_SRST.
set -eu
flag=/run/ckks-altboot-srst.once
hook=/usr/lib/systemd/system-shutdown/ckks-altboot-srst
case "${1-}" in
  --cancel)
    rm -f "$flag"
    echo 'ALTBOOT_CANCELLED: next normal reboot is not intercepted.'
    exit 0 ;;
  '') ;;
  *) echo 'Usage: sh prepare_altboot_srst.sh [--cancel]' >&2; exit 1 ;;
esac
fail() { echo "ERROR: $*" >&2; exit 1; }
[ "$(id -u)" = 0 ] || fail 'Run as root on the VEK280 Linux console.'
[ "$(uname -m)" = aarch64 ] || fail 'Expected the aarch64 board, not the PC.'
tr '\000' '\n' < /sys/firmware/devicetree/base/model | grep -qi vek280 || fail 'Expected VEK280 device tree.'
[ -d /run/systemd/system ] || fail 'systemd is not the active init system.'
[ -x /usr/lib/systemd/systemd-shutdown ] || fail 'systemd-shutdown is unavailable.'
[ -x /usr/sbin/devmem ] || fail '/usr/sbin/devmem is unavailable.'
# /usr must remain accessible from the root file system during final shutdown.
if awk '$2 == "/usr" {found=1} END {exit !found}' /proc/mounts; then
  fail 'Separate /usr mount: do not use this shutdown hook.'
fi
sd=/run/media/mmcblk0p1
awk -v sd="$sd" '$1 == "/dev/mmcblk0p1" && $2 == sd && $3 == "vfat" {found=1} END {exit !found}' /proc/mounts || fail 'Expected mounted SD boot partition.'
hash_check() {
  [ -f "$1" ] || fail "Missing $1"
  task_sum=$(sha256sum "$1")
  [ "${task_sum%% *}" = "$2" ] || fail "SHA256 mismatch: $1"
}
hash_check "$sd/boot0001.bin" c12b4f6cc3de7af24aad06862c2fc88c1b594d01cca496fdd88afbb9cafa89ac
hash_check "$sd/BOOT.BIN" e73f7a483fea0db0e8398f7f8290ff914428ec4cf2cb632b3d86277218371afd
hash_check "$sd/boot0002.bin" e73f7a483fea0db0e8398f7f8290ff914428ec4cf2cb632b3d86277218371afd
hash_check "$sd/Image" 79359c3f0af65cef3dbabab725b156a4b7b1925f781ab42f2f997be70f6dc86c
hash_check "$sd/boot.scr" ac5f09919439a3a94cf9729ac070d26f6e637acae91796f74f6416d3c10e748e
for task_override in system.dtb uEnv.txt image.ub; do
  [ ! -e "$sd/$task_override" ] || fail "Boot override present: $task_override"
done
echo 'PASS: candidate, original BOOT.BIN, backup, Image and boot.scr checksums.'
echo 'Current MultiBoot (read only):'
/usr/sbin/devmem 0xf1110004 32
echo 'Current CRP_RST_PS (read only):'
/usr/sbin/devmem 0xf126031c 32
mkdir -p /usr/lib/systemd/system-shutdown
task_tmp=$(mktemp /usr/lib/systemd/system-shutdown/.ckks-altboot-srst.XXXXXX)
trap 'rm -f "$task_tmp"' EXIT HUP INT TERM
cat > "$task_tmp" <<'CKKS_SHUTDOWN_HOOK'
#!/bin/sh
# CKKS one-shot slot 1 selector; unarmed on every later boot.
[ "${1-}" = reboot ] || exit 0
flag=/run/ckks-altboot-srst.once
[ -f "$flag" ] || exit 0
IFS= read -r task_token < "$flag" || exit 0
[ "$task_token" = CKKS_SLOT1_C12B4F6C ] || exit 0
# Consume first. /run is RAM, so a failure cannot persist into another boot.
rm -f "$flag" || exit 1
root_ro=no
sd_rw=no
while read -r task_dev task_mnt task_fs task_opts task_rest; do
  if [ "$task_mnt" = / ]; then
    case ",$task_opts," in *,ro,*) root_ro=yes ;; esac
  fi
  case "$task_dev" in
    /dev/mmcblk*) case ",$task_opts," in *,rw,*) sd_rw=yes ;; esac ;;
  esac
done < /proc/mounts
if [ "$root_ro" != yes ] || [ "$sd_rw" = yes ]; then
  echo 'CKKS_SRST_ABORT: storage still writable; use normal reboot.' >&2
  exit 1
fi
# SD filesystem partition selector is F in bits 31:28; slot is in bits 20:0.
/usr/sbin/devmem 0xf1110004 32 0xf0000001 || exit 1
task_readback=$(/usr/sbin/devmem 0xf1110004 32) || exit 1
case "$task_readback" in
  0xF0000001|0xf0000001) ;;
  *) echo 'CKKS_SRST_ABORT: MultiBoot readback is not SD filesystem slot 1.' >&2; exit 1 ;;
esac
echo 'CKKS_SRST: filesystems read-only; MultiBoot=0xF0000001 (SD filesystem slot 1); triggering PMC_SRST.' >&2
# Same write as XPlmi_SoftResetHandler; bypass the normal firmware reboot path.
/usr/sbin/devmem 0xf126031c 32 0x8
echo 'CKKS_SRST: reset write returned; normal reboot may follow.' >&2
exit 1
CKKS_SHUTDOWN_HOOK
chmod 755 "$task_tmp"
if [ -e "$hook" ] || [ -L "$hook" ]; then
  [ ! -L "$hook" ] && [ -f "$hook" ] || fail 'Unexpected shutdown hook type; not overwriting it.'
  if ! cmp -s "$task_tmp" "$hook"; then
    task_old_sum=$(sha256sum "$hook")
    [ "${task_old_sum%% *}" = d44c1ab418adacaf37d8532907f37be4b3385ba0a5a0247c01b5b3223ce8263f ] || fail 'A different shutdown hook already exists; not overwriting it.'
    # Only replace our exact previous version; disarm its RAM request first.
    rm -f "$flag"
    mv "$task_tmp" "$hook"
  fi
else
  mv "$task_tmp" "$hook"
fi
printf '%s\n' CKKS_SLOT1_C12B4F6C > "$flag"
chmod 600 "$flag"
sync
echo 'ALTBOOT_SRST_READY: one-shot hook armed; no reset has occurred.'
echo 'Next: keep COM4 open and run sync, then reboot.'
echo 'Cancel before reboot: sh prepare_altboot_srst.sh --cancel'
