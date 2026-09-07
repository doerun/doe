import assert from 'node:assert/strict';
import { mkdtempSync, rmSync, symlinkSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { tmpdir } from 'node:os';

const [addonPath, nativePath, alternatePath] = process.argv.slice(2).map(path => resolve(path));
const loaded = { exports: {} };
process.dlopen(loaded, addonPath);
const addon = loaded.exports;
assert.throws(() => addon.loadLibrary(42), /path string/);
assert.throws(() => addon.createInstance(), /Library not loaded/);
assert.throws(() => addon.loadLibrary('/does-not-exist/libwebgpu_doe.so'), /Failed to load/);
assert.throws(() => addon.loadLibrary('/lib/x86_64-linux-gnu/libc.so.6'), /required symbols/);
assert.throws(() => addon.createInstance(), /Library not loaded/);
assert.equal(addon.loadLibrary(nativePath), true);
const instance = addon.createInstance();
assert(instance);
const directory = mkdtempSync(join(tmpdir(), 'doe-library-identity-'));
try {
  const alias = join(directory, 'same-library.so');
  symlinkSync(nativePath, alias);
  assert.equal(addon.loadLibrary(alias), true);
  assert.throws(() => addon.loadLibrary(alternatePath), /different Doe native library/);
  assert.equal(addon.loadLibrary(nativePath), true);
  addon.instanceRelease(instance);
} finally {
  rmSync(directory, { recursive: true });
}
console.log('PASS: failed load retry, exact loaded library, aliases, conflicting library rejection, original instance release');
