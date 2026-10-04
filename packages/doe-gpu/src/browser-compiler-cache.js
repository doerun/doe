// Verified byte storage; the caller supplies the trusted digest and byte budget.

export async function sha256(bytes) {
  const digest = await crypto.subtle.digest('SHA-256', bytes);
  return Array.from(new Uint8Array(digest), (value) => value.toString(16).padStart(2, '0'))
    .join('');
}

export async function acquireCompilerBytes({ url, sha256: expected, byteLength, cache }) {
  if (!/^[a-f0-9]{64}$/.test(expected) || !Number.isSafeInteger(byteLength)
      || byteLength < 1 || byteLength > 8 * 1024 * 1024) {
    throw new TypeError('A trusted SHA-256 and bounded byteLength are required');
  }
  const timings = { cacheReadMs: 0, downloadMs: 0, verifyMs: 0, cacheWriteMs: 0 };
  let directory;
  let cacheStatus = cache ? 'unavailable' : 'disabled';
  const filename = `doe-wgsl-${expected}.wasm`;
  if (cache) {
    const started = performance.now();
    try {
      directory = await (await navigator.storage.getDirectory())
        .getDirectoryHandle('doe-compiler-v1', { create: true });
      const file = await (await directory.getFileHandle(filename)).getFile();
      if (file.size !== byteLength) throw new Error('Cached compiler size mismatch');
      const bytes = await file.arrayBuffer();
      timings.cacheReadMs = performance.now() - started;
      const verifyStart = performance.now();
      const verified = await sha256(bytes) === expected;
      timings.verifyMs += performance.now() - verifyStart;
      if (!verified) throw new Error('Cached compiler digest mismatch');
      return { bytes, timings, cacheStatus: 'verified-hit', bytesDownloaded: 0 };
    } catch (error) {
      timings.cacheReadMs = performance.now() - started;
      cacheStatus = directory ? (error.name === 'NotFoundError' ? 'miss' : 'rejected')
        : 'unavailable';
      if (directory && cacheStatus === 'rejected') {
        await directory.removeEntry(filename).catch(() => {});
      }
    }
  }
  const downloadStart = performance.now();
  const response = await fetch(url, { cache: 'no-store', credentials: 'omit' });
  if (!response.ok) throw new Error(`Compiler download failed: HTTP ${response.status}`);
  // Stream into a bounded allocation; a missing/misleading Content-Length cannot
  // allow an untrusted endpoint to exhaust the Worker before verification.
  const bytes = new Uint8Array(byteLength);
  const reader = response.body.getReader();
  let received = 0;
  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      if (received + value.byteLength > byteLength) throw new Error('Compiler exceeds byte budget');
      bytes.set(value, received);
      received += value.byteLength;
    }
  } finally {
    await reader.cancel().catch(() => {});
  }
  timings.downloadMs = performance.now() - downloadStart;
  if (received !== byteLength) throw new Error('Compiler size mismatch');
  const verifyStart = performance.now();
  const verified = await sha256(bytes) === expected;
  timings.verifyMs += performance.now() - verifyStart;
  if (!verified) throw new Error('Compiler digest mismatch');
  if (directory) {
    const writeStart = performance.now();
    try {
      const handle = await directory.getFileHandle(filename, { create: true });
      const writable = await handle.createWritable();
      try {
        await writable.write(bytes);
        await writable.close();
      } catch (error) {
        await writable.abort().catch(() => {});
        throw error;
      }
      cacheStatus = `${cacheStatus}-stored`;
    } catch (error) {
      cacheStatus = `${cacheStatus}-write-failed:${error.name}`;
    }
    timings.cacheWriteMs = performance.now() - writeStart;
  }
  return { bytes, timings, cacheStatus, bytesDownloaded: received };
}
