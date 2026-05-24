#!/usr/bin/env bash
# Builds a minimal bzImage + busybox initramfs for the fractal demo.
# Runs ONCE in the islo sandbox; the result is cached in the sandbox snapshot
# so subsequent `make demo` calls reuse it.
#
# Intentionally small — we want the boot-to-fractal time to be < 5 seconds.

set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
BUILD="$HERE/build"
mkdir -p "$BUILD"

KVER="${KVER:-6.6.30}"
BBVER="${BBVER:-1.36.1}"

# 1. Kernel
if [[ ! -f "$BUILD/bzImage" ]]; then
    cd "$BUILD"
    curl -LO "https://cdn.kernel.org/pub/linux/kernel/v6.x/linux-${KVER}.tar.xz"
    tar xf "linux-${KVER}.tar.xz"
    cd "linux-${KVER}"
    make tinyconfig
    # Enable framebuffer + VESA so /dev/fb0 exists for our asm binary.
    scripts/config -e CONFIG_FB -e CONFIG_FB_VESA -e CONFIG_FB_VGA16 \
        -e CONFIG_DEVTMPFS -e CONFIG_DEVTMPFS_MOUNT \
        -e CONFIG_PRINTK -e CONFIG_TTY -e CONFIG_SERIAL_8250 \
        -e CONFIG_SERIAL_8250_CONSOLE
    make olddefconfig
    make -j"$(nproc)" bzImage
    cp arch/x86/boot/bzImage "$BUILD/bzImage"
fi

# 2. Initramfs
if [[ ! -f "$BUILD/initramfs.cpio.gz" ]]; then
    cd "$BUILD"
    mkdir -p initramfs/{bin,sbin,dev,proc,sys}
    if [[ ! -x initramfs/bin/busybox ]]; then
        curl -L "https://busybox.net/downloads/binaries/${BBVER}-defconfig-multiarch-musl/busybox-x86_64" \
            -o initramfs/bin/busybox
        chmod +x initramfs/bin/busybox
        ( cd initramfs/bin && for app in sh mount ls cat echo sleep ; do ln -sf busybox $app ; done )
    fi
    ( cd initramfs && find . | cpio -o -H newc 2>/dev/null | gzip > "$BUILD/initramfs.cpio.gz" )
fi

echo "✓ microvm assets ready in $BUILD"
