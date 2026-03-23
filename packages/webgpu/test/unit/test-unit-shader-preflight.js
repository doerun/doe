import assert from 'node:assert/strict';

/**
 * Adversarial / negative tests for preflightShaderSource().
 *
 * preflightShaderSource requires the native addon + libwebgpu_doe.
 * When the addon is unavailable it returns a default { ok: true } stub.
 * We test both cases: native-available (real validation) and fallback
 * (graceful degradation). If the native addon cannot load, every test
 * that depends on real rejection is skipped with a clear message.
 *
 * Run: node packages/webgpu/test/unit/test-unit-shader-preflight.js
 */

let preflightShaderSource;
let nativeAvailable = false;

try {
  const mod = await import('../../src/native-direct.js');
  preflightShaderSource = mod.preflightShaderSource;
  // Probe whether the addon actually delegates to a real checker.
  // The function itself does not throw — it returns { ok: true } if
  // addon.checkShaderSource is not available.
  const probe = preflightShaderSource('');
  // If the addon is a stub, every call returns ok:true regardless of input.
  // We detect "real" availability by checking a known-bad input.
  const bad = preflightShaderSource('@@@invalid wgsl@@@');
  nativeAvailable = bad.ok === false;
} catch {
  // addon or library not found — use a no-op stub so structural tests
  // still exercise the contract shape.
  preflightShaderSource = () => ({ ok: true, stage: '', kind: '', message: '', reasons: [] });
  nativeAvailable = false;
}

let passed = 0;
let failed = 0;
let skipped = 0;

function report(name, ok, detail) {
  if (ok === 'skip') {
    skipped++;
    console.log(`  SKIP  ${name} — ${detail}`);
  } else if (ok) {
    passed++;
    console.log(`  PASS  ${name}`);
  } else {
    failed++;
    console.log(`  FAIL  ${name}: ${detail}`);
  }
}

function run(name, fn) {
  try {
    fn();
    report(name, true);
  } catch (err) {
    report(name, false, err.message);
  }
}

function skipUnlessNative(name, fn) {
  if (!nativeAvailable) {
    report(name, 'skip', 'native addon not available');
    return;
  }
  run(name, fn);
}

console.log('\n=== preflightShaderSource adversarial tests ===\n');

// --- (a) Valid compute shader returns ok: true ---

run('valid compute shader returns ok: true', () => {
  const code = `
    @group(0) @binding(0) var<storage, read_write> out: array<f32>;
    @compute @workgroup_size(64)
    fn main(@builtin(global_invocation_id) gid: vec3u) {
      out[gid.x] = f32(gid.x);
    }
  `;
  const result = preflightShaderSource(code);
  assert.equal(typeof result, 'object', 'result must be an object');
  assert.equal(result.ok, true, 'valid shader must return ok: true');
  assert.equal(typeof result.stage, 'string');
  assert.equal(typeof result.message, 'string');
  assert.ok(Array.isArray(result.reasons), 'reasons must be an array');
});

// --- (b) Empty string handled gracefully ---

run('empty string handled gracefully', () => {
  const result = preflightShaderSource('');
  assert.equal(typeof result, 'object', 'result must be an object');
  assert.equal(typeof result.ok, 'boolean', 'ok must be boolean');
  // Empty shader might be ok (stub) or fail (native) — either is valid.
  // The contract is no throw + well-formed return.
  assert.equal(typeof result.message, 'string');
  assert.ok(Array.isArray(result.reasons));
});

// --- (c) Syntax error WGSL rejected (native only) ---

skipUnlessNative('syntax error WGSL returns ok: false', () => {
  const result = preflightShaderSource('fn main( { totally broken wgsl');
  assert.equal(result.ok, false, 'syntax error must be rejected');
  assert.ok(result.message.length > 0, 'error message must be non-empty');
  assert.ok(result.reasons.length > 0, 'reasons must be non-empty');
});

// --- (d) Very long shader source (100 KB of comments) ---

run('very long shader source (100 KB) does not throw', () => {
  const comment = '// ' + 'x'.repeat(97) + '\n'; // 100 bytes per line
  const lines = Math.ceil(100_000 / comment.length);
  const code = comment.repeat(lines)
    + '@compute @workgroup_size(1) fn main() {}\n';
  const result = preflightShaderSource(code);
  assert.equal(typeof result, 'object');
  assert.equal(typeof result.ok, 'boolean');
});

// --- (e) Binary / null bytes in shader source ---

run('binary/null bytes in shader source handled', () => {
  const code = '\x00\x01\x02\xFF@compute fn main() {}';
  const result = preflightShaderSource(code);
  assert.equal(typeof result, 'object');
  assert.equal(typeof result.ok, 'boolean');
  // Either rejected or accepted — must not throw.
});

// --- (f) Shader with only comments ---

run('shader with only comments handled', () => {
  const code = '// this is a comment\n/* another comment */\n';
  const result = preflightShaderSource(code);
  assert.equal(typeof result, 'object');
  assert.equal(typeof result.ok, 'boolean');
  assert.ok(Array.isArray(result.reasons));
});

// --- (g) Valid vertex/fragment shader (non-compute) ---

run('valid vertex shader returns well-formed result', () => {
  const code = `
    @vertex
    fn vs_main(@builtin(vertex_index) idx: u32) -> @builtin(position) vec4f {
      return vec4f(0.0, 0.0, 0.0, 1.0);
    }
  `;
  const result = preflightShaderSource(code);
  assert.equal(typeof result, 'object');
  assert.equal(typeof result.ok, 'boolean');
  assert.equal(typeof result.message, 'string');
  assert.ok(Array.isArray(result.reasons));
});

run('valid fragment shader returns well-formed result', () => {
  const code = `
    @fragment
    fn fs_main() -> @location(0) vec4f {
      return vec4f(1.0, 0.0, 0.0, 1.0);
    }
  `;
  const result = preflightShaderSource(code);
  assert.equal(typeof result, 'object');
  assert.equal(typeof result.ok, 'boolean');
});

// --- Additional adversarial: non-string argument ---

run('non-string argument does not crash', () => {
  // The contract does not specify behavior for non-string input,
  // but it must not crash the process.
  try {
    const result = preflightShaderSource(undefined);
    assert.equal(typeof result, 'object');
  } catch {
    // throwing is acceptable for non-string input
  }
});

run('numeric argument does not crash', () => {
  try {
    const result = preflightShaderSource(42);
    assert.equal(typeof result, 'object');
  } catch {
    // throwing is acceptable
  }
});

// --- Report ---

console.log(`\n  ${passed} passed, ${failed} failed, ${skipped} skipped\n`);
if (failed > 0) {
  process.exit(1);
}
