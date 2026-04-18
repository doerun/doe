// Worker-thread depth sort. Computes view-space z per splat against the
// provided view matrix, then returns indices in back-to-front order (largest z
// first — since the WebGPU clip space we use has -z forward, "largest z" means
// "furthest from camera").
//
// Radix sort over quantized depth keys keeps this O(n) per frame and allocates
// no garbage on the hot path after the first message.

let positions = null; // Float32Array, length 3 * count
let count = 0;

// Pre-allocated scratch buffers (kept across messages to avoid GC churn).
let indices = null;
let depthKeys = null;
let histogram = null;
let prefix = null;
let sorted = null;
let tmp = null;

const RADIX_BITS = 8;
const RADIX_BUCKETS = 1 << RADIX_BITS;
const RADIX_MASK = RADIX_BUCKETS - 1;

self.addEventListener("message", (ev) => {
  const msg = ev.data;
  if (msg.kind === "splats") {
    positions = new Float32Array(msg.positions);
    count = (positions.length / 3) | 0;
    // Resize scratch
    indices = new Uint32Array(count);
    for (let i = 0; i < count; i = i + 1) indices[i] = i;
    depthKeys = new Uint32Array(count);
    histogram = new Uint32Array(RADIX_BUCKETS);
    prefix = new Uint32Array(RADIX_BUCKETS);
    sorted = new Uint32Array(count);
    tmp = new Uint32Array(count);
    self.postMessage({ kind: "splats-ready", count });
    return;
  }
  if (msg.kind === "sort") {
    if (positions === null) return;
    const v = msg.view; // 16 f32 (column-major)
    const m2 = v[2], m6 = v[6], m10 = v[10], m14 = v[14];
    // View-space z = m2 * x + m6 * y + m10 * z + m14 (column-major lookup).

    // Compute depth range for quantization (one linear pass).
    let zMin = Infinity;
    let zMax = -Infinity;
    for (let i = 0; i < count; i = i + 1) {
      const o = i * 3;
      const z = m2 * positions[o] + m6 * positions[o + 1] + m10 * positions[o + 2] + m14;
      if (z < zMin) zMin = z;
      if (z > zMax) zMax = z;
    }
    const span = Math.max(zMax - zMin, 1e-6);
    // Quantize to 24 bits. Invert so larger z (farther) becomes smaller key —
    // we want back-to-front rendering, i.e. furthest splat first.
    const scale = 16777215 / span;
    for (let i = 0; i < count; i = i + 1) {
      const o = i * 3;
      const z = m2 * positions[o] + m6 * positions[o + 1] + m10 * positions[o + 2] + m14;
      depthKeys[i] = 16777215 - (((z - zMin) * scale) | 0);
    }

    // 3-pass LSD radix sort on the 24-bit keys.
    let src = indices;
    let dst = sorted;
    for (let shift = 0; shift < 24; shift = shift + RADIX_BITS) {
      histogram.fill(0);
      for (let i = 0; i < count; i = i + 1) {
        const k = (depthKeys[src[i]] >> shift) & RADIX_MASK;
        histogram[k] = histogram[k] + 1;
      }
      prefix[0] = 0;
      for (let b = 1; b < RADIX_BUCKETS; b = b + 1) {
        prefix[b] = prefix[b - 1] + histogram[b - 1];
      }
      for (let i = 0; i < count; i = i + 1) {
        const idx = src[i];
        const k = (depthKeys[idx] >> shift) & RADIX_MASK;
        dst[prefix[k]] = idx;
        prefix[k] = prefix[k] + 1;
      }
      const swap = src;
      src = dst;
      dst = swap;
    }
    // After 3 passes (24 bits / 8), the final sorted order is in `src`.
    // Copy to a fresh transferable Uint32Array so the main thread can keep it.
    const out = new Uint32Array(count);
    out.set(src);
    // Keep the double-buffer pair alive for the next message.
    indices = src;
    sorted = (src === indices) ? sorted : src;
    // Actually normalize: after even number of passes src and dst have
    // deterministic identity; rather than track, just reset indices to a
    // stable 0..count-1 so next sort starts from a clean identity (the keys
    // change per camera anyway so stability is irrelevant).
    for (let i = 0; i < count; i = i + 1) indices[i] = i;
    self.postMessage({ kind: "sorted", indices: out.buffer, generation: msg.generation }, [out.buffer]);
  }
});
