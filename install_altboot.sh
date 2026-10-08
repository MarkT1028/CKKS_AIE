#!/bin/sh
# Stage a separate SD MultiBoot candidate. Never replace BOOT.BIN or reboot.
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
sha256sum -c SHA256SUMS
bootdir=/run/media/mmcblk0p1
original_sha=e73f7a483fea0db0e8398f7f8290ff914428ec4cf2cb632b3d86277218371afd
grep -q " $bootdir vfat " /proc/mounts || {
    echo "FAIL: SD FAT boot partition is not mounted at $bootdir" >&2; exit 1;
}
actual_sha=$(sha256sum "$bootdir/BOOT.BIN" | cut -d ' ' -f 1)
test "$actual_sha" = "$original_sha" || {
    echo 'FAIL: current BOOT.BIN differs from the supplied snapshot; nothing changed.' >&2; exit 1;
}
for name in system.dtb uEnv.txt image.ub; do
    test ! -e "$bootdir/$name" || {
        echo "FAIL: $name overrides the embedded boot configuration; inspect it first." >&2; exit 1;
    }
done
test "$(sha256sum "$bootdir/Image" | cut -d ' ' -f 1)" = \
    79359c3f0af65cef3dbabab725b156a4b7b1925f781ab42f2f997be70f6dc86c
test "$(sha256sum "$bootdir/boot.scr" | cut -d ' ' -f 1)" = \
    ac5f09919439a3a94cf9729ac070d26f6e637acae91796f74f6416d3c10e748e
needed_kb=$(( ($(wc -c < boot0001.bin) + $(wc -c < "$bootdir/BOOT.BIN")) / 1024 + 4096 ))
available_kb=$(df -Pk "$bootdir" | awk 'NR==2 {print $4}')
test "$available_kb" -gt "$needed_kb" || {
    echo 'FAIL: insufficient free space on the SD boot partition.' >&2; exit 1;
}
check_slot() {
    if test -e "$bootdir/$2"; then
        cmp "$1" "$bootdir/$2" || {
            echo "FAIL: $2 is occupied by a different image; it will not be overwritten." >&2; exit 1;
        }
    fi
}
check_slot boot0001.bin boot0001.bin
check_slot "$bootdir/BOOT.BIN" boot0002.bin
task_tmp=
trap 'test -z "$task_tmp" || rm -f "$task_tmp"' EXIT HUP INT TERM
stage_slot() {
    if test ! -e "$bootdir/$2"; then
        task_tmp=$(mktemp "$bootdir/.ckks-stage-XXXXXX")
        cp "$1" "$task_tmp"
        cmp "$1" "$task_tmp"
        sync
        mv "$task_tmp" "$bootdir/$2"
        task_tmp=
    fi
}
# Put the known original fallback in slot 2 before staging candidate slot 1.
stage_slot "$bootdir/BOOT.BIN" boot0002.bin
stage_slot boot0001.bin boot0001.bin
sync
test "$(sha256sum "$bootdir/BOOT.BIN" | cut -d ' ' -f 1)" = "$original_sha"
printf '%s\n' 'ALTBOOT_READY: slot 1 staged; original BOOT.BIN preserved; slot 2 is an exact backup.'
printf '%s\n' 'No reset or MultiBoot register change was performed. Next step is manual COM4 U-Boot selection.'
