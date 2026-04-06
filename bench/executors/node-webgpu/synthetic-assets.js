import { readFileSync } from 'node:fs';
import { homedir } from 'node:os';
import { join, resolve } from 'node:path';

const CACHE_ENV_VAR = 'DOE_BENCH_ASSET_CACHE_DIR';
const DEFAULT_CACHE_DIR_SUFFIX = 'doe/bench_synthetic_assets';

export function resolveSyntheticAssetCacheRoot() {
  const override = typeof process.env[CACHE_ENV_VAR] === 'string'
    ? process.env[CACHE_ENV_VAR].trim()
    : '';
  if (override) {
    return resolve(override);
  }
  return join(homedir(), '.cache', DEFAULT_CACHE_DIR_SUFFIX);
}

export function resolveSyntheticAssetPath(cacheNamespace, cacheKey) {
  const namespace = typeof cacheNamespace === 'string' ? cacheNamespace.trim() : '';
  const key = typeof cacheKey === 'string' ? cacheKey.trim() : '';
  if (!namespace || !key) {
    throw new Error('synthetic asset descriptors require non-empty cacheNamespace and cacheKey');
  }
  return join(resolveSyntheticAssetCacheRoot(), namespace, `${key}.bin`);
}

export function readSyntheticAssetData({ cacheNamespace, cacheKey, sizeBytes }) {
  const path = resolveSyntheticAssetPath(cacheNamespace, cacheKey);
  const payload = readFileSync(path);
  if (!Number.isInteger(sizeBytes) || sizeBytes <= 0) {
    throw new Error('synthetic asset descriptors require positive sizeBytes');
  }
  if (payload.byteLength !== sizeBytes) {
    throw new Error(
      `synthetic asset ${cacheNamespace}/${cacheKey} expected ${sizeBytes} bytes, got ${payload.byteLength}`,
    );
  }
  return Uint8Array.from(payload);
}
