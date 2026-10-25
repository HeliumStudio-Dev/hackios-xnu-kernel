#!/usr/bin/env bash
# Bounded RAM-only MPSS/WLAN bring-up; never flashes or enables UFS writes.
set -euo pipefail
cd "$(dirname "$0")/.."
win_fastboot=/mnt/c/Users/Helium-Studio/Documents/platform-tools/fastboot.exe
usbipd='/mnt/c/Program Files/usbipd-win/usbipd.exe'
loader_only=false
if [[ ${1:-} == --loader-only ]]; then loader_only=true; shift; fi
boot_image=${1:-xnu-usb.img}
for file in "$boot_image" out/host-bin/fastboot; do
    test -f "$file" || { printf 'Missing %s\n' "$file" >&2; exit 1; }
done
if ! "$loader_only"; then
test -f out/raphael/wifi-bootstrap.apfs || { printf 'Missing Wi-Fi RAM image\n' >&2; exit 1; }
kernel=xnu-src/xnu-8796.121.2/BUILD/obj/DEVELOPMENT_ARM64_BCM2837/mach.development.bcm2837
[[ "$kernel" -nt xnu/files/bsd/dev/hakios.wifi.c ]] || { printf 'Wi-Fi source is newer than the kernel; build first.\n' >&2; exit 1; }
for file in out/raphael/wifi-boot/fw/*; do
    [[ out/raphael/wifi-bootstrap.apfs -nt "$file" ]] || { printf 'RAM firmware image is stale: %s\n' "$file" >&2; exit 1; }
done
fi
if "$win_fastboot" devices | tr -d '\r' | rg -q '^d11b018e[[:space:]]'; then
    "$win_fastboot" -s d11b018e boot "$(wslpath -w "$boot_image")"
fi
for ((attempt=0; attempt<30; attempt++)); do
    if sudo -n /usr/bin/fastboot devices | rg -q '^xnuloader[[:space:]]'; then break; fi
    state=$("$usbipd" list)
    if printf '%s\n' "$state" | rg -q '^5-2[[:space:]].*xnuloader.*Shared'; then
        "$usbipd" attach --wsl --busid 5-2
    fi
    sleep 1
done
sudo -n /usr/bin/fastboot devices | rg -q '^xnuloader[[:space:]]' || {
    printf 'Loader USB is unavailable; return the phone to Bootloader.\n' >&2; exit 1;
}
if "$loader_only"; then
    sudo -n /usr/bin/fastboot -s xnuloader getvar version
    exit 0
fi
export PATH="$PWD/out/host-bin:$PATH"
./xl ramdisk out/raphael/wifi-bootstrap.apfs
export XL_SECS=60 XL_FOLLOW=1 XL_FOLLOW_KEEP=1
export XL_CMDLINE='gic_timer_irq=19 bootcpu=7 cpus=1 gpu=0 wifi_step=14 wifi_new=99 wifi_pause=0 wifi_watch=1 wifi_wait=10 wifi_listen=15 wifi_ask=1 wifi_bdf=bd_f11cn.bin wifi_smmu=2 wifi_pdr=1 wifi_diag=1 wifi_return=1 adsp=0 ufs=0 ufs_write=0'
if [[ ${WIFI_TEST_DRIVER:-0} == 1 ]]; then
    XL_CMDLINE=${XL_CMDLINE/wifi_step=14/wifi_step=15}
    XL_CMDLINE+=' wifi_lx=2 wifi_scan=1'
    export XL_SECS=120
fi
./xl run
