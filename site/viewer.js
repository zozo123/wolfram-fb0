// viewer.js — thin client for the live sandbox panes.
//
// Two streams, two panes:
//   #fb-stream  — framebuffer from the qemu boot in the sandbox.
//                 STUB: we don't ship a real VNC/RFB decoder here. If a
//                 ?sandbox=<wss-url> param is supplied we open the socket and
//                 treat incoming binary messages as JPEG/PNG frames (the islo
//                 share gateway is configured to transcode RFB → image frames
//                 for browser preview). With no param we render a static
//                 placeholder so the page works on a cold GitHub Pages load.
//   #bpf-stream — JSONL eBPF events. Real wire format. ?bpf=<wss-url> attaches;
//                 with no param we cycle a 10-line sample every second so the
//                 pane is never empty during demos.
//
// No deps. ES6+. Static-host friendly (no build step).

(() => {
  const qs = new URLSearchParams(location.search);
  const sandboxUrl = qs.get("sandbox");
  const bpfUrl     = qs.get("bpf");

  // ────────────────────────────────────────────────────────────────────────
  // Framebuffer pane
  // ────────────────────────────────────────────────────────────────────────
  const fbPane = document.getElementById("fb-stream");
  if (fbPane) {
    if (sandboxUrl) {
      mountLiveFramebuffer(fbPane, sandboxUrl);
    } else {
      mountPosterFramebuffer(fbPane);
    }
  }

  function mountLiveFramebuffer(pane, url) {
    // REAL: opens a WebSocket to the islo-share gateway. The gateway pushes
    // image frames (binary blobs) as the VM's framebuffer updates.
    pane.classList.remove("placeholder");
    pane.textContent = "";
    pane.style.padding = "0";
    pane.style.minHeight = "320px";
    pane.style.background = "#000";
    pane.style.border = "1px solid #1c1c24";
    pane.style.borderRadius = "6px";
    pane.style.overflow = "hidden";

    const img = document.createElement("img");
    img.alt = "live framebuffer";
    img.style.cssText = "width:100%;height:100%;object-fit:contain;image-rendering:pixelated;display:block;";
    pane.appendChild(img);

    const status = document.createElement("div");
    status.style.cssText = "position:relative;font:0.78rem ui-monospace,Menlo,monospace;color:#7c3aed;padding:0.4rem 0.6rem;background:#0a0a0f;border-top:1px solid #1c1c24;";
    status.textContent = "connecting…";
    pane.appendChild(status);

    let ws;
    try {
      ws = new WebSocket(url);
      ws.binaryType = "blob";
    } catch (e) {
      status.textContent = "connect failed: " + e.message;
      return;
    }

    let lastUrl = null;
    ws.addEventListener("open",  () => { status.textContent = "● live  " + url; });
    ws.addEventListener("close", () => { status.textContent = "○ closed"; });
    ws.addEventListener("error", () => { status.textContent = "✗ error — falling back to poster"; mountPosterFramebuffer(pane); });
    ws.addEventListener("message", (ev) => {
      if (!(ev.data instanceof Blob)) return; // text frames ignored for now
      if (lastUrl) URL.revokeObjectURL(lastUrl);
      lastUrl = URL.createObjectURL(ev.data);
      img.src = lastUrl;
    });
  }

  function mountPosterFramebuffer(pane) {
    // STUB: pre-recorded look. Draws a procedural "no-signal" pattern in the
    // accent colors so the pane isn't dead while no sandbox is attached.
    pane.classList.remove("placeholder");
    pane.textContent = "";
    pane.style.padding = "0";
    pane.style.background = "#000";
    pane.style.minHeight = "240px";

    const canvas = document.createElement("canvas");
    canvas.width = 640;
    canvas.height = 240;
    canvas.style.cssText = "width:100%;height:auto;display:block;image-rendering:pixelated;";
    pane.appendChild(canvas);

    const cap = document.createElement("div");
    cap.style.cssText = "font:0.78rem ui-monospace,Menlo,monospace;color:#8a8a96;padding:0.4rem 0.6rem;border-top:1px solid #1c1c24;background:#0a0a0f;";
    cap.innerHTML = "no sandbox attached — pass <code>?sandbox=&lt;wss://…&gt;</code> to mount a live stream";
    pane.appendChild(cap);

    const ctx = canvas.getContext("2d");
    const W = canvas.width, H = canvas.height;
    let t = 0;
    function frame() {
      const img = ctx.createImageData(W, H);
      for (let y = 0; y < H; y++) {
        for (let x = 0; x < W; x++) {
          const v = ((x ^ y) + t) & 0xff;
          const i = (y * W + x) * 4;
          // accent purple-ish gradient
          img.data[i + 0] = (v * 124) >> 8;     // R toward 7c
          img.data[i + 1] = (v * 58)  >> 8;     // G toward 3a
          img.data[i + 2] = (v * 237) >> 8;     // B toward ed
          img.data[i + 3] = 255;
        }
      }
      ctx.putImageData(img, 0, 0);
      ctx.fillStyle = "rgba(10,10,15,0.65)";
      ctx.fillRect(0, H - 28, W, 28);
      ctx.fillStyle = "#22c55e";
      ctx.font = "12px ui-monospace, Menlo, monospace";
      ctx.fillText("[poster]  fb0 stream offline — fork a sandbox to see the real fractal", 12, H - 10);
      t = (t + 2) & 0xff;
    }
    frame();
    setInterval(frame, 120);
  }

  // ────────────────────────────────────────────────────────────────────────
  // eBPF trace pane
  // ────────────────────────────────────────────────────────────────────────
  const bpfPane = document.getElementById("bpf-stream");
  if (bpfPane) {
    if (bpfUrl) {
      mountLiveBpf(bpfPane, bpfUrl);
    } else {
      mountSampleBpf(bpfPane);
    }
  }

  function mountLiveBpf(pane, url) {
    // REAL: bpftrace JSONL events streamed over WebSocket from islo share.
    pane.classList.remove("placeholder");
    pane.textContent = "[trace] connecting to " + url + " …\n";
    let ws;
    try { ws = new WebSocket(url); }
    catch (e) { pane.textContent += "[trace] connect failed: " + e.message + "\n"; return; }
    ws.addEventListener("open",  () => appendBpf(pane, "[trace] ● live\n"));
    ws.addEventListener("close", () => appendBpf(pane, "[trace] ○ closed\n"));
    ws.addEventListener("error", () => appendBpf(pane, "[trace] ✗ error — falling back to sample\n"));
    ws.addEventListener("message", (ev) => {
      const line = typeof ev.data === "string" ? ev.data : "[binary frame ignored]";
      appendBpf(pane, formatBpfLine(line));
    });
  }

  function mountSampleBpf(pane) {
    // STUB: 10 representative events from a real run, recycled every second so
    // the pane scrolls during the demo.
    pane.classList.remove("placeholder");
    pane.textContent = "";
    const sample = [
      {ts: "0.0001", evt: "execve", arg: "/dist/rule30.elf"},
      {ts: "0.0003", evt: "openat", arg: "/dev/fb0 O_RDWR"},
      {ts: "0.0004", evt: "ioctl",  arg: "FBIOGET_VSCREENINFO"},
      {ts: "0.0005", evt: "mmap",   arg: "fb0  3686400 bytes  PROT_RW MAP_SHARED"},
      {ts: "0.0010", evt: "uprobe", arg: "rule30.s:_start"},
      {ts: "0.0011", evt: "uprobe", arg: "rule30.s:row_loop  rdi=512"},
      {ts: "0.0021", evt: "write",  arg: "fb0[0..1024] = 0x00ff3cdc"},
      {ts: "0.0034", evt: "uprobe", arg: "rule30.s:next_row  rax=320"},
      {ts: "0.0090", evt: "munmap", arg: "fb0"},
      {ts: "0.0092", evt: "exit",   arg: "code=0"}
    ];
    let idx = 0;
    const MAX_LINES = 120;
    function tick() {
      const e = sample[idx % sample.length];
      appendBpf(pane, formatBpfLine(JSON.stringify(e)), MAX_LINES);
      idx++;
    }
    tick();
    setInterval(tick, 1000);
  }

  function appendBpf(pane, line, maxLines = 400) {
    pane.textContent += line;
    // Trim from the top so the buffer never grows unbounded.
    const lines = pane.textContent.split("\n");
    if (lines.length > maxLines) {
      pane.textContent = lines.slice(lines.length - maxLines).join("\n");
    }
    pane.scrollTop = pane.scrollHeight;
  }

  function formatBpfLine(raw) {
    try {
      const j = JSON.parse(raw);
      const ts  = String(j.ts  ?? "?").padStart(7);
      const evt = String(j.evt ?? "?").padEnd(7);
      const arg = String(j.arg ?? "");
      return `[${ts}] ${evt} ${arg}\n`;
    } catch {
      return raw.endsWith("\n") ? raw : raw + "\n";
    }
  }
})();
