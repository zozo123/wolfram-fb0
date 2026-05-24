#!/usr/bin/env python3
"""bridge_bpf.py — bpftrace JSONL → WebSocket bridge for wolfram-fb0.

Spawns `bpftrace bpf/trace.bt -o jsonl` as a subprocess, reads its stdout one
line at a time, and broadcasts each line as a text WebSocket frame to every
connected client. The public site's `viewer.js` parses each line as JSON and
renders it into <pre id="bpf-stream">.

`--mock` skips bpftrace entirely and emits a synthetic JSONL stream so the
demo pane keeps scrolling even when no fractal is running (or when running
locally without root + kernel BPF privileges).

CLI:
  python3 harness/bridge_bpf.py [--port 8911] [--mock]
                                [--trace-file bpf/trace.bt]
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import socket
import socketserver
import struct
import subprocess
import sys
import threading
import time
from typing import Iterator

WS_MAGIC = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

_clients_lock = threading.Lock()
_clients: list[socket.socket] = []


# ─── Tiny RFC 6455 server (text frames only) ────────────────────────────────

def _ws_handshake(sock: socket.socket) -> bool:
    sock.settimeout(5.0)
    buf = b""
    while b"\r\n\r\n" not in buf:
        chunk = sock.recv(4096)
        if not chunk:
            return False
        buf += chunk
        if len(buf) > 16384:
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
    accept = base64.b64encode(
        hashlib.sha1((key + WS_MAGIC).encode("ascii")).digest()
    ).decode("ascii")
    sock.sendall((
        "HTTP/1.1 101 Switching Protocols\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Accept: {accept}\r\n\r\n"
    ).encode("ascii"))
    sock.settimeout(None)
    return True


def _ws_encode_text(text: str) -> bytes:
    """Wrap UTF-8 text in a single un-fragmented text frame (opcode 0x1)."""
    payload = text.encode("utf-8")
    header = bytearray([0x81])
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
    def handle(self) -> None:
        if not _ws_handshake(self.request):
            return
        with _clients_lock:
            _clients.append(self.request)
        try:
            while True:
                data = self.request.recv(4096)
                if not data:
                    return
                if data and (data[0] & 0x0F) == 0x8:  # client close frame
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


def _broadcast(line: str) -> None:
    wire = _ws_encode_text(line)
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


# ─── Event sources ──────────────────────────────────────────────────────────

def _bpftrace_lines(trace_file: str) -> Iterator[str]:
    """Spawn `bpftrace -o jsonl <trace>` and yield stdout lines. bpftrace
    needs root in practice; if launch fails (ENOENT, EACCES) the caller falls
    back to mock mode."""
    # `-q` silences the "Attaching N probes" banner. `-o jsonl` is documented
    # as the JSONL output mode in recent bpftrace; we pass it explicitly even
    # though `trace.bt` already emits JSON via printf — it's a no-op then.
    proc = subprocess.Popen(
        ["bpftrace", "-q", trace_file, "-o", "jsonl"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=1,
        text=True,
    )
    assert proc.stdout is not None
    try:
        for line in proc.stdout:
            line = line.rstrip("\n")
            if line:
                yield line
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=2.0)
        except (OSError, subprocess.TimeoutExpired):
            try:
                proc.kill()
            except OSError:
                pass


def _mock_lines() -> Iterator[str]:
    """Emit a synthetic JSONL stream matching the schema viewer.js expects.

    Keys: ts (float seconds since start, stringified), evt (one of execve,
    openat, ioctl, mmap, uprobe, write, munmap, exit, tick), arg (free-form
    description string). This intentionally mirrors `mountSampleBpf` in
    viewer.js so the live pane is visually indistinguishable from the cold
    pane during development.
    """
    cycle = [
        ("execve", "/dist/rule30.elf"),
        ("openat", "/dev/fb0 O_RDWR"),
        ("ioctl",  "FBIOGET_VSCREENINFO"),
        ("mmap",   "fb0  3686400 bytes  PROT_RW MAP_SHARED"),
        ("uprobe", "rule30.s:_start"),
        ("uprobe", "rule30.s:row_loop  rdi=512"),
        ("write",  "fb0[0..1024] = 0x00ff3cdc"),
        ("uprobe", "rule30.s:next_row  rax=320"),
        ("munmap", "fb0"),
        ("exit",   "code=0"),
    ]
    t0 = time.monotonic()
    i = 0
    while True:
        evt, arg = cycle[i % len(cycle)]
        ts = f"{time.monotonic() - t0:.4f}"
        yield json.dumps({"ts": ts, "evt": evt, "arg": arg})
        i += 1
        time.sleep(0.2)


def _produce_loop(args: argparse.Namespace) -> None:
    if args.mock:
        source = _mock_lines()
    else:
        try:
            source = _bpftrace_lines(args.trace_file)
        except (OSError, FileNotFoundError) as e:
            sys.stderr.write(f"[bridge_bpf] bpftrace unavailable ({e}); using mock\n")
            source = _mock_lines()
    for line in source:
        if _clients:
            _broadcast(line)


# ─── Entry point ────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--port", type=int,
                    default=int(os.environ.get("WOLFRAM_BPF_BRIDGE_PORT", "8911")))
    ap.add_argument("--mock", action="store_true",
                    help="emit synthetic JSONL events; never spawn bpftrace")
    ap.add_argument("--trace-file",
                    default=os.environ.get("WOLFRAM_BPF_TRACE", "bpf/trace.bt"))
    args = ap.parse_args()

    server = _ThreadedWSServer(("0.0.0.0", args.port), _WSHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f"ready on :{args.port}", flush=True)
    try:
        _produce_loop(args)
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()


if __name__ == "__main__":
    main()
