// Rule 30, animated row-by-row in the browser.
// Same algorithm as src/rule30_reference.s (the agent's target).
// Pre-computes the full grid once, then animates the reveal with a brighter
// frontier line tracking the newest row. Holds when complete, then loops.

(() => {
  const canvas = document.getElementById("rule30");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  const W = canvas.width, H = canvas.height;
  const img = ctx.createImageData(W, H);

  const ON       = [220, 60, 255];
  const OFF      = [10, 10, 18];
  const FRONTIER = [255, 180, 255];

  const ROWS_PER_FRAME = 2;   // 320 / 2 ≈ 160 frames ≈ 2.7 s at 60 fps growth
  const HOLD_FRAMES    = 60;  // ~1 s pause on the completed pattern before looping

  // Pre-compute the full Rule 30 grid as Uint8Arrays — fast, runs once.
  const grid = [];
  {
    let row = new Uint8Array(W);
    row[W >> 1] = 1;
    for (let y = 0; y < H; y++) {
      grid.push(row);
      const next = new Uint8Array(W);
      for (let x = 0; x < W; x++) {
        const l = row[(x - 1 + W) % W];
        const c = row[x];
        const r = row[(x + 1) % W];
        next[x] = l ^ (c | r);
      }
      row = next;
    }
  }

  function paintRow(y, onColor) {
    const r = grid[y];
    for (let x = 0; x < W; x++) {
      const i = (y * W + x) * 4;
      const c = r[x] ? onColor : OFF;
      img.data[i]     = c[0];
      img.data[i + 1] = c[1];
      img.data[i + 2] = c[2];
      img.data[i + 3] = 255;
    }
  }

  function clearImg() {
    for (let i = 0; i < img.data.length; i += 4) {
      img.data[i]     = OFF[0];
      img.data[i + 1] = OFF[1];
      img.data[i + 2] = OFF[2];
      img.data[i + 3] = 255;
    }
  }

  let drawnUpTo = 0;
  let holdLeft  = 0;

  function reset() {
    clearImg();
    drawnUpTo = 0;
    holdLeft  = 0;
    ctx.putImageData(img, 0, 0);
  }

  function frame() {
    if (drawnUpTo < H) {
      for (let k = 0; k < ROWS_PER_FRAME && drawnUpTo < H; k++) {
        if (drawnUpTo > 0) paintRow(drawnUpTo - 1, ON);  // downgrade prior frontier
        paintRow(drawnUpTo, FRONTIER);
        drawnUpTo++;
      }
      ctx.putImageData(img, 0, 0);
    } else if (holdLeft === 0) {
      // Just finished — recolor final frontier to plain ON, start the hold.
      paintRow(H - 1, ON);
      ctx.putImageData(img, 0, 0);
      holdLeft = HOLD_FRAMES;
    } else {
      holdLeft--;
      if (holdLeft <= 0) reset();
    }
    requestAnimationFrame(frame);
  }

  reset();
  requestAnimationFrame(frame);
})();
