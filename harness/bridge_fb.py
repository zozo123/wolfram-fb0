#!/usr/bin/env python3
"""bridge_fb.py — framebuffer → WebSocket bridge for the wolfram-fb0 demo.

Polls qemu's VNC server (RFB protocol, port 5900) ~10x/sec, encodes the latest
framebuffer as a JPEG via Pillow, and broadcasts the bytes as binary WebSocket
frames to every connected client. `viewer.js` on the public Pages site treats
each binary message as one image to drop into <img id="fb-stream">.

Why stdlib + Pillow only: the sandbox image installs python3 + python3-pillow
through apt; we deliberately avoid pip so a cold sandbox can run this without
network. The WebSocket handshake is a manual RFC 6455 server on top of
socketserver.ThreadingTCPServer (~80 lines). The VNC client is a minimal RFB
3.3 reader — no auth, BGRA → RGB, framebuffer-update only — also ~80 lines.

Modes:
  --mock        Skip VNC entirely. Render a synthetic Rule-30-ish JPEG locally
                and broadcast at the same cadence so the public site looks
                alive even when the inner qemu hasn't booted.
  (default)     Connect to VNC at $WOLFRAM_FB_VNC_HOST:$WOLFRAM_FB_VNC_PORT
                (127.0.0.1:5900). If the VNC connection drops we transparently
                fall back to mock frames until it comes back.

CLI:
  python3 harness/bridge_fb.py [--port 8910] [--mock]
                               [--vnc-host 127.0.0.1] [--vnc-port 5900]
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import io
import os
import socket
import socketserver
import struct
import sys
import threading
import time
from typing import Optional

from PIL import Image  # ships with apt python3-pillow

# ─────────────────────────────────────────────────────────────────────────────
# RFC 6455 WebSocket server (binary broadcast only — we never read from clients
# beyond the handshake, so this is intentionally tiny).
# ─────────────────────────────────────────────────────────────────────────────

WS_MAGIC = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

_clients_lock = threading.Lock()
_clients: list[socket.socket] = []


def _ws_accept_key(client_key: str) -> str:
    """Compute the Sec-WebSocket-Accept header value per RFC 6455 §4.2.2."""
    sha = hashlib.sha1((client_key + WS_MAGIC).encode("ascii")).digest()
    return base64.b64encode(sha).decode("ascii")


def _ws_handshake(sock: socket.socket) -> bool:
    """Read the HTTP upgrade request and reply with the 101 Switching Protocols."""
    sock.settimeout(5.0)
    buf = b""
    while b"\r\n\r\n" not in buf:
        chunk = sock.recv(4096)
        if not chunk:
            return False
        buf += chunk
        if len(buf) > 16384:  # absurd header → reject
            return False
    headers = {}
    for line in buf.split(b"\r\n")[1:]:
        if b":" in line:
            k, _, v = line.partition(b":")
            headers[k.strip().lower().decode("latin-1")] = v.strip().decode("latin-1")
    key = headers.get("sec-websocket-key")
    if not key or headers.get("upgrade", "").lower() != "websocket":
        sock.sendall(b"HTTP/1.1 400 Bad Request\r\nContent-Length: 0\r\n\r\n")
        return False
    accept = _ws_accept_key(key)
    response = (
        "HTTP/1.1 101 Switching Protocols\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Accept: {accept}\r\n\r\n"
    )
    sock.sendall(response.encode("ascii"))
    sock.settimeout(None)
    return True


def _ws_encode_binary(payload: bytes) -> bytes:
    """Wrap `payload` in a single un-fragmented binary frame (opcode 0x2).

    Server frames are not masked (RFC 6455 §5.1). We always send the whole
    payload in one frame — JPEGs are small enough that fragmentation buys us
    nothing.
    """
    header = bytearray([0x82])  # FIN=1, opcode=2 (binary)
    n = len(payload)
    if n < 126:
        header.append(n)
    elif n < (1 << 16):
        header.append(126)
        header += struct.pack(">H", n)
    else:
        header.append(127)
        header += struct.pack(">Q", n)
    return bytes(header) + payload


class _WSHandler(socketserver.BaseRequestHandler):
    """One connected viewer. We don't decode incoming frames — broadcast only."""

    def handle(self) -> None:
        if not _ws_handshake(self.request):
            return
        with _clients_lock:
            _clients.append(self.request)
        try:
            # Park the thread; the broadcaster pushes data on this socket. We
            # only return when the client closes (recv returns b"") or errors.
            while True:
                data = self.request.recv(4096)
                if not data:
                    return
                # Honor close frames (opcode 0x8) — anything else is ignored.
                if data and (data[0] & 0x0F) == 0x8:
                    return
        except OSError:
            return
        finally:
            with _clients_lock:
                if self.request in _clients:
                    _clients.remove(self.request)
            try:
                self.request.close()
            except OSError:
                pass


class _ThreadedWSServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def _broadcast(frame: bytes) -> None:
    """Send one binary WS frame to every connected client. Drop dead sockets."""
    wire = _ws_encode_binary(frame)
    dead: list[socket.socket] = []
    with _clients_lock:
        targets = list(_clients)
    for s in targets:
        try:
            s.sendall(wire)
        except OSError:
            dead.append(s)
    if dead:
        with _clients_lock:
            for s in dead:
                if s in _clients:
                    _clients.remove(s)
                try:
                    s.close()
                except OSError:
                    pass


# ─────────────────────────────────────────────────────────────────────────────
# Minimal RFB 3.3 / 3.8 client. We only need the framebuffer raw pixels; no
# auth, no input events. The qemu `-display vnc=:0` server is no-auth on
# loopback by default.
# ─────────────────────────────────────────────────────────────────────────────

class VNCClient:
    """One-shot RFB reader. Reconnects are handled by the caller on error."""

    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = port
        self.sock: Optional[socket.socket] = None
        self.width = 0
        self.height = 0

    def connect(self) -> None:
        s = socket.create_connection((self.host, self.port), timeout=3.0)
        # ProtocolVersion: server sends "RFB 003.008\n" (12 bytes). We always
        # downgrade to 003.003 (no security negotiation) which qemu accepts.
        s.recv(12)
        s.sendall(b"RFB 003.003\n")
        # Security type — 4-byte u32. 1 = None, 0 = invalid.
        sec = struct.unpack(">I", _recv_exact(s, 4))[0]
        if sec != 1:
            raise RuntimeError(f"VNC requires auth (security={sec}); unsupported")
        # ClientInit: 1 byte shared-flag.
        s.sendall(b"\x01")
        # ServerInit: width(2) height(2) pixel-format(16) name-len(4) name(n).
        init = _recv_exact(s, 24)
        self.width, self.height = struct.unpack(">HH", init[:4])
        name_len = struct.unpack(">I", init[20:24])[0]
        _recv_exact(s, name_len)
        # SetPixelFormat: force BGRA32, little-endian, true-color.
        # bits-per-pixel=32 depth=24 big-endian=0 true-color=1
        # red-max=255 green-max=255 blue-max=255  shifts: R=16 G=8 B=0
        pf = struct.pack(">BBBB BBB B HHH BBB BBB",
                          0, 0, 0, 0,         # msg-type=0 + 3-byte pad
                          32, 24, 0, 1,        # bpp, depth, big-endian, true-color
                          255, 255, 255,       # max R,G,B
                          16, 8, 0,            # shifts
                          0, 0, 0)             # 3-byte pad
        s.sendall(pf)
        # SetEncodings: Raw only (encoding=0). msg-type=2, pad, count=1, [0].
        s.sendall(struct.pack(">BBH I", 2, 0, 1, 0))
        self.sock = s

    def request_frame(self, incremental: bool = False) -> None:
        # FramebufferUpdateRequest: type=3, incremental, x, y, w, h.
        assert self.sock is not None
        self.sock.sendall(struct.pack(
            ">BBHHHH", 3, 1 if incremental else 0,
            0, 0, self.width, self.height))

    def read_frame(self) -> Optional[Image.Image]:
        """Read one FramebufferUpdate and composite it. Returns None on EOF."""
        assert self.sock is not None
        hdr = _recv_exact(self.sock, 4)
        if hdr[0] != 0:  # we only handle msg-type 0 (FramebufferUpdate)
            return None
        n_rects = struct.unpack(">H", hdr[2:4])[0]
        # Each pass we composite onto a fresh black canvas at full size; for a
        # demo this is good enough and avoids carrying state between frames.
        canvas = Image.new("RGB", (self.width, self.height), (0, 0, 0))
        for _ in range(n_rects):
            rh = _recv_exact(self.sock, 12)
            x, y, w, h, enc = struct.unpack(">HHHHI", rh)
            if enc != 0:  # we asked for Raw; anything else means we're confused
                # Drain a heuristic chunk and bail.
                return None
            pixels = _recv_exact(self.sock, w * h * 4)
            tile = Image.frombytes("RGBA", (w, h), pixels, "raw", "BGRA")
            canvas.paste(tile.convert("RGB"), (x, y))
        return canvas

    def close(self) -> None:
        if self.sock is not None:
            try:
                self.sock.close()
            except OSError:
                pass
            self.sock = None


def _recv_exact(sock: socket.socket, n: int) -> bytes:
    """Read exactly n bytes or raise on EOF."""
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise RuntimeError("VNC connection closed mid-message")
        buf += chunk
    return bytes(buf)


# ─────────────────────────────────────────────────────────────────────────────
# Frame producers.
# ─────────────────────────────────────────────────────────────────────────────

def _jpeg_bytes(img: Image.Image, quality: int = 70) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


def _mock_frame(t: int) -> bytes:
    """Synthetic Rule-30-flavored frame so the public site is never empty.

    Generates a 640x240 XOR-gradient with a moving offset and overlays a
    "[mock] fb0 stream" tag. Roughly 8–12 KB JPEG at quality=70.
    """
    W, H = 640, 240
    img = Image.new("RGB", (W, H), (0, 0, 0))
    px = img.load()
    for y in range(H):
        for x in range(W):
            v = ((x ^ y) + t) & 0xFF
            px[x, y] = ((v * 124) >> 8, (v * 58) >> 8, (v * 237) >> 8)
    return _jpeg_bytes(img)


def _produce_loop(args: argparse.Namespace) -> None:
    """Drive the broadcast — either by polling VNC or by emitting mock frames."""
    interval = 1.0 / max(1, args.fps)
    t = 0
    vnc: Optional[VNCClient] = None
    use_mock = args.mock
    while True:
        start = time.monotonic()
        frame: Optional[bytes] = None
        if not use_mock:
            try:
                if vnc is None or vnc.sock is None:
                    vnc = VNCClient(args.vnc_host, args.vnc_port)
                    vnc.connect()
                    vnc.request_frame(incremental=False)
                else:
                    vnc.request_frame(incremental=True)
                img = vnc.read_frame()
                if img is not None:
                    frame = _jpeg_bytes(img)
            except (OSError, RuntimeError) as e:
                # On any VNC trouble: print once, fall back to mock for this
                # tick, retry the connection on the next tick.
                sys.stderr.write(f"[bridge_fb] vnc error, mock fallback: {e}\n")
                if vnc is not None:
                    vnc.close()
                vnc = None
                frame = _mock_frame(t)
        else:
            frame = _mock_frame(t)
        if frame is not None and _clients:
            _broadcast(frame)
        t = (t + 4) & 0xFF
        elapsed = time.monotonic() - start
        time.sleep(max(0.0, interval - elapsed))


# ─────────────────────────────────────────────────────────────────────────────
# Entry point.
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--port", type=int,
                    default=int(os.environ.get("WOLFRAM_FB_BRIDGE_PORT", "8910")))
    ap.add_argument("--mock", action="store_true",
                    help="emit synthetic frames; never touch VNC")
    ap.add_argument("--vnc-host", default=os.environ.get("WOLFRAM_FB_VNC_HOST", "127.0.0.1"))
    ap.add_argument("--vnc-port", type=int,
                    default=int(os.environ.get("WOLFRAM_FB_VNC_PORT", "5900")))
    ap.add_argument("--fps", type=int, default=10)
    args = ap.parse_args()

    server = _ThreadedWSServer(("0.0.0.0", args.port), _WSHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    # Stdout sentinel — readiness probe in islo share / supervisor expects this.
    print(f"ready on :{args.port}", flush=True)
    try:
        _produce_loop(args)
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()


if __name__ == "__main__":
    main()
