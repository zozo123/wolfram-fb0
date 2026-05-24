#!/usr/bin/env bash
# qemu/boot.sh — boot a minimal Linux inside the islo sandbox VM that immediately
# execs the agent-built fractal binary on a real Linux framebuffer.
#
# This is the "money shot": real /dev/fb0, real kernel, real syscalls; the
# whole thing runs inside the islo VM and streams out via `islo share`.

set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/.." && pwd)"
BUILD="$HERE/build"
DIST="${WOLFRAM_DIST:-$REPO/dist}"

mkdir -p "$BUILD"

KERNEL="$BUILD/bzImage"
INITRD="$BUILD/initramfs.cpio.gz"
TARGET="${1:-rule30}"

# Acquire a tiny kernel + busybox-based initramfs (built in the sandbox setup
# step, cached as a snapshot). First-run will build them; subsequent runs reuse.
if [[ ! -f "$KERNEL" || ! -f "$INITRD" ]]; then
    bash "$HERE/build-microvm.sh"
fi

# Lay our fractal binary into the initramfs root before boot.
WORK="$BUILD/rootfs"
rm -rf "$WORK" && mkdir -p "$WORK"
( cd "$WORK" && zcat "$INITRD" | cpio -idmu )
cp "$DIST/${TARGET}.elf" "$WORK/fractal"
chmod +x "$WORK/fractal"

# init runs the fractal directly on /dev/fb0.
cat > "$WORK/init" <<'INIT'
#!/bin/sh
mount -t proc proc /proc
mount -t sysfs sys /sys
mount -t devtmpfs dev /dev
echo "[wolfram-fb0] booting fractal on /dev/fb0…"
exec /fractal --fb /dev/fb0
INIT
chmod +x "$WORK/init"

( cd "$WORK" && find . | cpio -o -H newc 2>/dev/null | gzip > "$BUILD/initramfs.${TARGET}.cpio.gz" )

PORT="${WOLFRAM_FB_BRIDGE_PORT:-8910}"

# Boot it. -display vnc exposes the framebuffer on a port; islo share publishes
# that port. No KVM needed on the inner boot — the islo VM is the KVM layer.
exec qemu-system-x86_64 \
    -kernel "$KERNEL" \
    -initrd "$BUILD/initramfs.${TARGET}.cpio.gz" \
    -append "console=ttyS0 quiet" \
    -nographic \
    -vga std \
    -display "vnc=:0,websocket=${PORT}" \
    -m 64M
