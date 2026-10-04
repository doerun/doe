#!/usr/bin/env node
// Local browser example server; exposes only the package's example/src/assets.
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { resolve, dirname, extname, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const types = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css',
  '.json': 'application/json', '.wasm': 'application/wasm', '.wgsl': 'text/plain' };
const server = createServer(async (request, response) => {
  try {
    const pathname = decodeURIComponent(new URL(request.url, 'http://localhost').pathname);
    const target = pathname === '/' || pathname === '/examples/browser-compiler/'
      ? '/examples/browser-compiler/index.html' : pathname;
    const path = resolve(root, `.${target}`);
    if (!['examples/browser-compiler', 'src', 'assets'].some((allowed) =>
      path.startsWith(resolve(root, allowed) + sep))) throw new Error('Unsupported path');
    const bytes = await readFile(path);
    response.writeHead(200, { 'Content-Type': types[extname(path)] ?? 'application/octet-stream',
      'Cache-Control': 'no-store' });
    response.end(bytes);
  } catch {
    response.writeHead(404);
    response.end();
  }
});
server.listen(0, '127.0.0.1', () => {
  console.log(`Doe-assisted WebGPU: http://127.0.0.1:${server.address().port}/examples/browser-compiler/`);
});
server.on('error', (error) => { console.error(error); process.exitCode = 1; });
