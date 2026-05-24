// chart.js — vanilla SVG convergence chart.
//
// Reads /iterations/index.json and renders binary_size + pixel_diff_pct
// over iterations for each target. Two y-axes, no libraries.
//
//   rule30 → purple  (--accent  #7c3aed)
//   mandel → green   (--accent-2 #22c55e)
//   julia  → orange  (         #f97316)
//
// Solid line = binary_size (left axis). Dashed line = pixel_diff_pct (right axis).

(() => {
  const mount = document.getElementById("convergence-chart");
  if (!mount) return;

  const COLORS = { rule30: "#7c3aed", mandel: "#22c55e", julia: "#f97316" };
  const BG = "#0a0a0f", FG = "#e8e8ec", DIM = "#8a8a96", LINE = "#1c1c24";
  const SVG_NS = "http://www.w3.org/2000/svg";

  // Resolve the JSON path relative to the document so the page works whether
  // it's served from the repo root or a subdirectory (GitHub Pages project sites).
  const here = location.pathname.replace(/[^/]+$/, "");
  const dataUrl = (here.endsWith("/site/") ? here.replace(/site\/$/, "") : here) + "iterations/index.json";

  fetch(dataUrl, { cache: "no-cache" })
    .then((r) => { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
    .then(render)
    .catch((e) => {
      mount.classList.add("placeholder");
      mount.textContent = "chart unavailable: " + e.message;
    });

  function render(data) {
    mount.classList.remove("placeholder");
    mount.textContent = "";
    mount.style.cssText += "background:#0e0e15;border:1px solid " + LINE + ";border-radius:8px;padding:0.75rem;display:block;";

    const W = 820, H = 360;
    const M = { t: 20, r: 56, b: 36, l: 56 };
    const innerW = W - M.l - M.r, innerH = H - M.t - M.b;

    const targets = Object.keys(data.targets || {});
    if (!targets.length) { mount.textContent = "no iterations yet."; return; }

    // Domains.
    let maxIter = 1, maxSize = 1;
    for (const t of targets) for (const it of data.targets[t]) {
      if (it.iter > maxIter) maxIter = it.iter;
      if (it.binary_size > maxSize) maxSize = it.binary_size;
    }
    maxSize = Math.max(maxSize, 1);

    const xs = (i) => M.l + ((i - 1) / Math.max(1, maxIter - 1)) * innerW;
    const ysSize = (b) => M.t + innerH - (b / maxSize) * innerH;
    const ysPct  = (p) => M.t + innerH - (Math.max(0, Math.min(100, p)) / 100) * innerH;

    const svg = el("svg", { xmlns: SVG_NS, viewBox: `0 0 ${W} ${H}`, width: "100%", height: "auto", role: "img", "aria-label": "convergence chart" });
    svg.style.display = "block";

    // Background panel.
    svg.appendChild(el("rect", { x: 0, y: 0, width: W, height: H, fill: BG, rx: 6 }));

    // Gridlines + left axis ticks (binary size).
    const sizeTicks = niceTicks(maxSize, 5);
    for (const v of sizeTicks) {
      const y = ysSize(v);
      svg.appendChild(el("line", { x1: M.l, y1: y, x2: W - M.r, y2: y, stroke: LINE, "stroke-width": 1 }));
      svg.appendChild(text(M.l - 8, y + 4, fmtBytes(v), { fill: DIM, "text-anchor": "end", "font-size": 10 }));
    }
    // Right axis ticks (pixel diff %).
    for (const v of [0, 25, 50, 75, 100]) {
      const y = ysPct(v);
      svg.appendChild(text(W - M.r + 8, y + 4, v + "%", { fill: DIM, "text-anchor": "start", "font-size": 10 }));
    }
    // X axis ticks.
    const xTicks = niceIntegerTicks(maxIter, 6);
    for (const v of xTicks) {
      const x = xs(v);
      svg.appendChild(el("line", { x1: x, y1: H - M.b, x2: x, y2: H - M.b + 4, stroke: DIM }));
      svg.appendChild(text(x, H - M.b + 16, String(v), { fill: DIM, "text-anchor": "middle", "font-size": 10 }));
    }

    // Axis labels.
    svg.appendChild(text(M.l, M.t - 6, "binary size", { fill: DIM, "font-size": 10, "font-family": "ui-monospace, Menlo, monospace" }));
    svg.appendChild(text(W - M.r, M.t - 6, "pixel diff %", { fill: DIM, "font-size": 10, "text-anchor": "end", "font-family": "ui-monospace, Menlo, monospace" }));
    svg.appendChild(text(W / 2, H - 6, "iteration", { fill: DIM, "font-size": 10, "text-anchor": "middle", "font-family": "ui-monospace, Menlo, monospace" }));

    // Lines and points, per target.
    const tooltip = makeTooltip();
    mount.appendChild(tooltip.node);

    for (const t of targets) {
      const color = COLORS[t] || "#cccccc";
      const iters = data.targets[t].slice().sort((a, b) => a.iter - b.iter);

      // binary size line — solid
      svg.appendChild(el("polyline", {
        points: iters.map((p) => `${xs(p.iter)},${ysSize(p.binary_size)}`).join(" "),
        fill: "none", stroke: color, "stroke-width": 2
      }));

      // pixel diff line — dashed
      svg.appendChild(el("polyline", {
        points: iters.map((p) => `${xs(p.iter)},${ysPct(p.pixel_diff_pct)}`).join(" "),
        fill: "none", stroke: color, "stroke-width": 1.5, "stroke-dasharray": "4 3", opacity: 0.85
      }));

      // Hover dots.
      for (const p of iters) {
        const cxV = xs(p.iter);
        const dotSize = el("circle", { cx: cxV, cy: ysSize(p.binary_size), r: 3.2, fill: color, stroke: BG, "stroke-width": 1 });
        const dotPct  = el("circle", { cx: cxV, cy: ysPct(p.pixel_diff_pct), r: 2.8, fill: BG, stroke: color, "stroke-width": 1.5 });
        for (const dot of [dotSize, dotPct]) {
          dot.style.cursor = "pointer";
          dot.addEventListener("mouseenter", (ev) => tooltip.show(ev, scoreLines(t, p, color)));
          dot.addEventListener("mousemove",  (ev) => tooltip.move(ev));
          dot.addEventListener("mouseleave", ()    => tooltip.hide());
        }
        svg.appendChild(dotSize);
        svg.appendChild(dotPct);
      }
    }

    // Legend.
    const legend = el("g", {});
    let lx = M.l;
    const ly = H - M.b + 28;
    for (const t of targets) {
      const color = COLORS[t] || "#cccccc";
      legend.appendChild(el("rect", { x: lx, y: ly - 8, width: 10, height: 10, fill: color, rx: 2 }));
      legend.appendChild(text(lx + 14, ly + 1, t, { fill: FG, "font-size": 11, "font-family": "ui-monospace, Menlo, monospace" }));
      lx += 14 + Math.max(40, t.length * 7) + 18;
    }
    // Don't draw legend off the bottom — fold it into the chart instead.
    legend.setAttribute("transform", `translate(0, ${-22})`);
    svg.appendChild(legend);

    mount.appendChild(svg);
  }

  // ── helpers ─────────────────────────────────────────────────────────────

  function el(name, attrs) {
    const n = document.createElementNS(SVG_NS, name);
    for (const k in attrs) n.setAttribute(k, attrs[k]);
    return n;
  }
  function text(x, y, s, attrs) {
    const n = el("text", Object.assign({ x, y }, attrs || {}));
    n.textContent = s;
    return n;
  }
  function niceTicks(max, n) {
    const step = Math.pow(10, Math.floor(Math.log10(max / n)));
    const m = max / n / step;
    const niceStep = (m < 1.5 ? 1 : m < 3 ? 2 : m < 7 ? 5 : 10) * step;
    const out = [];
    for (let v = 0; v <= max + niceStep / 2; v += niceStep) out.push(Math.round(v));
    return out;
  }
  function niceIntegerTicks(max, n) {
    const step = Math.max(1, Math.ceil(max / n));
    const out = [];
    for (let v = 1; v <= max; v += step) out.push(v);
    if (out[out.length - 1] !== max) out.push(max);
    return out;
  }
  function fmtBytes(b) {
    if (b >= 1024) return (b / 1024).toFixed(b % 1024 === 0 ? 0 : 1) + "K";
    return String(b);
  }

  function scoreLines(target, p, color) {
    // Convergence score: lower binary_size + lower diff is better. Show all.
    const score = p.assemble_ok
      ? (p.binary_size + p.pixel_diff_pct * 32).toFixed(0)
      : "—";
    return [
      { text: target + "  iter " + p.iter, color },
      { text: "binary_size: " + p.binary_size + " B" },
      { text: "pixel_diff:  " + p.pixel_diff_pct.toFixed(1) + "%" },
      { text: "assemble_ok: " + (p.assemble_ok ? "yes" : "no") },
      { text: "score:       " + score }
    ];
  }

  function makeTooltip() {
    const node = document.createElement("div");
    node.style.cssText = [
      "position:absolute", "pointer-events:none", "display:none",
      "background:#15151c", "border:1px solid #1c1c24", "border-radius:6px",
      "padding:0.5rem 0.7rem", "font:11px ui-monospace,Menlo,monospace",
      "color:#e8e8ec", "z-index:50", "white-space:pre",
      "box-shadow:0 4px 16px rgba(0,0,0,0.5)"
    ].join(";");
    // Position the parent relative so absolute positioning works.
    mount.style.position = "relative";
    function show(ev, lines) {
      node.innerHTML = "";
      for (const l of lines) {
        const row = document.createElement("div");
        row.textContent = l.text;
        if (l.color) row.style.color = l.color;
        node.appendChild(row);
      }
      node.style.display = "block";
      move(ev);
    }
    function move(ev) {
      const rect = mount.getBoundingClientRect();
      const x = ev.clientX - rect.left + 12;
      const y = ev.clientY - rect.top  + 12;
      node.style.left = x + "px";
      node.style.top  = y + "px";
    }
    function hide() { node.style.display = "none"; }
    return { node, show, move, hide };
  }
})();
