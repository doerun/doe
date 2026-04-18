// Parser for the community `.splat` binary format (antimatter15/splat).
//
// Per splat, 32 bytes packed little-endian:
//   0..12   position       3 × f32
//   12..24  scale          3 × f32  (already in linear units, not log-scale)
//   24..28  color          4 × u8   (r, g, b, opacity)
//   28..32  rotation       4 × u8   quaternion components remapped to [-1, 1] via (b - 128) / 128
//
// Total per-splat footprint on the GPU after unpacking is larger (see
// main.js::uploadSplats); the .splat format is a compact transport shape.

const BYTES_PER_SPLAT = 32;

export function parseSplatBuffer(arrayBuffer) {
  const bytes = arrayBuffer.byteLength;
  if (bytes === 0) throw new Error("empty splat buffer");
  if (bytes % BYTES_PER_SPLAT !== 0) {
    throw new Error(
      `splat buffer size ${bytes} is not a multiple of ${BYTES_PER_SPLAT}; ` +
      `file does not follow the 32-byte-per-splat community format`,
    );
  }
  const count = bytes / BYTES_PER_SPLAT;
  const view = new DataView(arrayBuffer);

  // Unpack to separate planar buffers. This is the shape uploadSplats wants.
  const positions = new Float32Array(count * 3);
  const scales = new Float32Array(count * 3);
  const rotations = new Float32Array(count * 4);
  const colors = new Uint8Array(count * 4);

  for (let i = 0; i < count; i = i + 1) {
    const o = i * BYTES_PER_SPLAT;
    positions[i * 3 + 0] = view.getFloat32(o + 0, true);
    positions[i * 3 + 1] = view.getFloat32(o + 4, true);
    positions[i * 3 + 2] = view.getFloat32(o + 8, true);

    scales[i * 3 + 0] = view.getFloat32(o + 12, true);
    scales[i * 3 + 1] = view.getFloat32(o + 16, true);
    scales[i * 3 + 2] = view.getFloat32(o + 20, true);

    colors[i * 4 + 0] = view.getUint8(o + 24);
    colors[i * 4 + 1] = view.getUint8(o + 25);
    colors[i * 4 + 2] = view.getUint8(o + 26);
    colors[i * 4 + 3] = view.getUint8(o + 27);

    // Quaternion is stored (w, x, y, z) as u8 centered at 128 mapping to
    // [-1, 1]. Renormalize after remap in case the quantization drift is
    // visible; the per-splat covariance math assumes a unit quaternion.
    const qw = (view.getUint8(o + 28) - 128) / 128;
    const qx = (view.getUint8(o + 29) - 128) / 128;
    const qy = (view.getUint8(o + 30) - 128) / 128;
    const qz = (view.getUint8(o + 31) - 128) / 128;
    const ql = Math.hypot(qw, qx, qy, qz) || 1;
    rotations[i * 4 + 0] = qw / ql;
    rotations[i * 4 + 1] = qx / ql;
    rotations[i * 4 + 2] = qy / ql;
    rotations[i * 4 + 3] = qz / ql;
  }

  return { count, positions, scales, rotations, colors };
}

export async function fetchAndParseSplat(url, onProgress) {
  const resp = await fetch(url);
  if (!resp.ok) throw new Error(`fetch ${url} failed: ${resp.status}`);
  const total = Number(resp.headers.get("Content-Length") || 0);
  if (!resp.body || total === 0 || !onProgress) {
    const buf = await resp.arrayBuffer();
    return parseSplatBuffer(buf);
  }
  const reader = resp.body.getReader();
  const chunks = [];
  let received = 0;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    chunks.push(value);
    received = received + value.byteLength;
    onProgress(received, total);
  }
  const merged = new Uint8Array(received);
  let offset = 0;
  for (const chunk of chunks) {
    merged.set(chunk, offset);
    offset = offset + chunk.byteLength;
  }
  return parseSplatBuffer(merged.buffer);
}
