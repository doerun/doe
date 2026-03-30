import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
const __dirname = dirname(fileURLToPath(import.meta.url));
export const addonPath = resolve(__dirname, 'bin', 'doe_napi.node');
export const libraryPath = resolve(__dirname, 'bin', 'libwebgpu_doe.so');
