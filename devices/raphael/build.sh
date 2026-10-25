#!/bin/bash
# Build the raphael port against the shared baseline; no flashing or image deployment.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
cd "$ROOT"
source devices/raphael/device.conf
export UEFI_TARGET UEFI_FD DTB FD_BASE FD_SIZE PAYLOAD_BASE
case ${1:-kernel} in
kernel)
    ./xnu-build.sh -j"${JOBS:-8}"
    ;;
loader) ./xnuloader/build.sh ;;
images)
    GL=1 REST=1 QUIET=1 OSLOG= RC="$ROOT/userland/rc.launchd" \
    RC_JOBS="$ROOT/userland/rc.jobs" userland/build.sh
    ;;
boot)
    mkdir -p out/raphael
    python3 xnuloader/mkpayload.py -o out/raphael/usb-payload.bin loader.efi=xnuloader/loader.efi --usb
    python3 mkxnuimg.py -p out/raphael/usb-payload.bin -o out/raphael/boot.img
    ;;
*) echo "usage: $0 {kernel|loader|images|boot}" >&2; exit 2 ;;
esac
