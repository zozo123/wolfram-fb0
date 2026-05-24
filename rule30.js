// Rule 30 — byte-for-byte equivalent to what the asm version writes to /dev/fb0.
// Kept ~40 lines so a reader can see the algorithm at a glance and match it to the asm.

(() => {
  const canvas = document.getElementById("rule30");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  const W = canvas.width, H = canvas.height;
  const img = ctx.createImageData(W, H);

  // Each pixel is one cell. Start with a single 1 in the middle of row 0.
  const row = new Uint8Array(W);
  row[W >> 1] = 1;

  const setPixel = (x, y, on) => {
    const i = (y * W + x) * 4;
    img.data[i + 0] = on ? 220 : 10;
    img.data[i + 1] = on ? 60  : 10;
    img.data[i + 2] = on ? 255 : 18;
    img.data[i + 3] = 255;
  };

  for (let y = 0; y < H; y++) {
    for (let x = 0; x < W; x++) setPixel(x, y, row[x]);
    // Rule 30: new = left XOR (center OR right). The asm version is the same bit trick.
    const next = new Uint8Array(W);
    for (let x = 0; x < W; x++) {
      const l = row[(x - 1 + W) % W];
      const c = row[x];
      const r = row[(x + 1) % W];
      next[x] = l ^ (c | r);
    }
    row.set(next);
  }
  ctx.putImageData(img, 0, 0);
})();
