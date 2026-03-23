import assert from 'node:assert/strict';
import {
  failValidation,
  describeResourceLabel,
  initResource,
  assertLiveResource,
  destroyResource,
  validatePositiveInteger,
  assertObject,
  assertArray,
  assertBoolean,
  assertString,
  assertNonEmptyString,
  assertIntegerInRange,
  assertOptionalIntegerInRange,
  MAX_SAFE_U64,
  UINT32_MAX,
} from '../../src/shared/resource-lifecycle.js';

/**
 * Adversarial / negative tests for pure resource-lifecycle utilities.
 * No GPU required — these are pure JS validation functions.
 *
 * Run: node packages/webgpu/test/unit/test-unit-resource-lifecycle.js
 */

let passed = 0;
let failed = 0;

function report(name, ok, detail) {
  if (ok) {
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

console.log('\n=== resource-lifecycle adversarial tests ===\n');

// ---------------------------------------------------------------
// (a) failValidation
// ---------------------------------------------------------------

run('failValidation throws Error with path and message', () => {
  assert.throws(
    () => failValidation('device.buffers[0]', 'size must be > 0'),
    (err) => {
      assert.ok(err instanceof Error);
      assert.ok(err.message.includes('device.buffers[0]'));
      assert.ok(err.message.includes('size must be > 0'));
      return true;
    },
  );
});

run('failValidation includes both path and message in output', () => {
  try {
    failValidation('root', 'bad');
    assert.fail('should have thrown');
  } catch (err) {
    assert.match(err.message, /root.*bad/);
  }
});

// ---------------------------------------------------------------
// (b) describeResourceLabel
// ---------------------------------------------------------------

run('describeResourceLabel returns _resourceLabel when present', () => {
  const obj = { _resourceLabel: 'myBuffer' };
  assert.equal(describeResourceLabel(obj), 'myBuffer');
});

run('describeResourceLabel returns fallback for plain object', () => {
  assert.equal(describeResourceLabel({}), 'resource');
  assert.equal(describeResourceLabel({}, 'device'), 'device');
});

run('describeResourceLabel returns fallback for null', () => {
  assert.equal(describeResourceLabel(null), 'resource');
  assert.equal(describeResourceLabel(null, 'queue'), 'queue');
});

run('describeResourceLabel returns fallback for undefined', () => {
  assert.equal(describeResourceLabel(undefined), 'resource');
});

// ---------------------------------------------------------------
// (c) initResource
// ---------------------------------------------------------------

run('initResource sets expected fields', () => {
  const target = {};
  const result = initResource(target, 'testLabel', 'ownerRef');
  assert.equal(result, target, 'returns same target');
  assert.equal(target._resourceLabel, 'testLabel');
  assert.equal(target._resourceOwner, 'ownerRef');
  assert.equal(target._destroyed, false);
});

run('initResource defaults owner to null', () => {
  const target = {};
  initResource(target, 'lbl');
  assert.equal(target._resourceOwner, null);
});

// ---------------------------------------------------------------
// (d) assertLiveResource
// ---------------------------------------------------------------

run('assertLiveResource passes for live resource', () => {
  const resource = { _native: {}, _destroyed: false, _resourceOwner: null };
  const native = assertLiveResource(resource, 'test');
  assert.equal(native, resource._native);
});

run('assertLiveResource throws for destroyed resource', () => {
  const resource = { _native: null, _destroyed: true, _resourceLabel: 'buf' };
  assert.throws(
    () => assertLiveResource(resource, 'test'),
    (err) => err instanceof Error && err.message.includes('destroyed'),
  );
});

run('assertLiveResource throws for non-object', () => {
  assert.throws(
    () => assertLiveResource(null, 'test'),
    (err) => err instanceof Error,
  );
  assert.throws(
    () => assertLiveResource(42, 'test'),
    (err) => err instanceof Error,
  );
});

run('assertLiveResource throws when owner is destroyed', () => {
  const owner = { _destroyed: true, _resourceLabel: 'device' };
  const resource = { _native: {}, _destroyed: false, _resourceOwner: owner };
  assert.throws(
    () => assertLiveResource(resource, 'test'),
    (err) => err instanceof Error && err.message.includes('destroyed'),
  );
});

// ---------------------------------------------------------------
// (e) destroyResource
// ---------------------------------------------------------------

run('destroyResource marks resource as destroyed', () => {
  let released = false;
  const resource = { _native: { handle: 1 }, _destroyed: false };
  destroyResource(resource, (_native) => { released = true; });
  assert.equal(resource._destroyed, true);
  assert.equal(resource._native, null);
  assert.equal(released, true);
});

run('destroyResource double-destroy is a no-op', () => {
  let releaseCount = 0;
  const resource = { _native: { handle: 1 }, _destroyed: false };
  destroyResource(resource, () => { releaseCount++; });
  destroyResource(resource, () => { releaseCount++; });
  assert.equal(releaseCount, 1, 'release callback must be called exactly once');
  assert.equal(resource._destroyed, true);
});

run('destroyResource no-op when _native is null', () => {
  let released = false;
  const resource = { _native: null, _destroyed: false };
  destroyResource(resource, () => { released = true; });
  assert.equal(released, false);
});

// ---------------------------------------------------------------
// (f) validatePositiveInteger
// ---------------------------------------------------------------

run('validatePositiveInteger accepts valid positive integers', () => {
  validatePositiveInteger(1, 'val');
  validatePositiveInteger(100, 'val');
  validatePositiveInteger(Number.MAX_SAFE_INTEGER, 'val');
});

run('validatePositiveInteger rejects 0', () => {
  assert.throws(
    () => validatePositiveInteger(0, 'val'),
    (err) => err instanceof Error && err.message.includes('positive integer'),
  );
});

run('validatePositiveInteger rejects negative', () => {
  assert.throws(
    () => validatePositiveInteger(-1, 'val'),
    (err) => err instanceof Error,
  );
  assert.throws(
    () => validatePositiveInteger(-100, 'val'),
    (err) => err instanceof Error,
  );
});

run('validatePositiveInteger rejects float', () => {
  assert.throws(
    () => validatePositiveInteger(1.5, 'val'),
    (err) => err instanceof Error,
  );
  assert.throws(
    () => validatePositiveInteger(0.9, 'val'),
    (err) => err instanceof Error,
  );
});

run('validatePositiveInteger rejects NaN', () => {
  assert.throws(
    () => validatePositiveInteger(NaN, 'val'),
    (err) => err instanceof Error,
  );
});

run('validatePositiveInteger rejects Infinity', () => {
  assert.throws(
    () => validatePositiveInteger(Infinity, 'val'),
    (err) => err instanceof Error,
  );
  assert.throws(
    () => validatePositiveInteger(-Infinity, 'val'),
    (err) => err instanceof Error,
  );
});

run('validatePositiveInteger rejects string', () => {
  assert.throws(
    () => validatePositiveInteger('5', 'val'),
    (err) => err instanceof Error,
  );
});

run('validatePositiveInteger rejects null/undefined', () => {
  assert.throws(
    () => validatePositiveInteger(null, 'val'),
    (err) => err instanceof Error,
  );
  assert.throws(
    () => validatePositiveInteger(undefined, 'val'),
    (err) => err instanceof Error,
  );
});

// ---------------------------------------------------------------
// (g) assertObject
// ---------------------------------------------------------------

run('assertObject accepts plain objects', () => {
  const result = assertObject({ a: 1 }, 'test', 'descriptor');
  assert.deepEqual(result, { a: 1 });
});

run('assertObject rejects null', () => {
  assert.throws(
    () => assertObject(null, 'test', 'desc'),
    (err) => err instanceof Error && err.message.includes('must be an object'),
  );
});

run('assertObject rejects arrays', () => {
  assert.throws(
    () => assertObject([1, 2], 'test', 'desc'),
    (err) => err instanceof Error && err.message.includes('must be an object'),
  );
});

run('assertObject rejects primitives', () => {
  assert.throws(() => assertObject(42, 'test', 'desc'), (err) => err instanceof Error);
  assert.throws(() => assertObject('str', 'test', 'desc'), (err) => err instanceof Error);
  assert.throws(() => assertObject(true, 'test', 'desc'), (err) => err instanceof Error);
  assert.throws(() => assertObject(undefined, 'test', 'desc'), (err) => err instanceof Error);
});

// ---------------------------------------------------------------
// (h) assertArray
// ---------------------------------------------------------------

run('assertArray accepts arrays', () => {
  const result = assertArray([1, 2, 3], 'test', 'entries');
  assert.deepEqual(result, [1, 2, 3]);
  assert.deepEqual(assertArray([], 'test', 'entries'), []);
});

run('assertArray rejects non-arrays', () => {
  assert.throws(
    () => assertArray({}, 'test', 'entries'),
    (err) => err instanceof Error && err.message.includes('must be an array'),
  );
  assert.throws(() => assertArray('str', 'test', 'entries'), (err) => err instanceof Error);
  assert.throws(() => assertArray(42, 'test', 'entries'), (err) => err instanceof Error);
  assert.throws(() => assertArray(null, 'test', 'entries'), (err) => err instanceof Error);
  assert.throws(() => assertArray(undefined, 'test', 'entries'), (err) => err instanceof Error);
});

// ---------------------------------------------------------------
// (i) assertBoolean
// ---------------------------------------------------------------

run('assertBoolean accepts booleans', () => {
  assert.equal(assertBoolean(true, 'test', 'flag'), true);
  assert.equal(assertBoolean(false, 'test', 'flag'), false);
});

run('assertBoolean rejects non-booleans', () => {
  assert.throws(
    () => assertBoolean(0, 'test', 'flag'),
    (err) => err instanceof Error && err.message.includes('must be a boolean'),
  );
  assert.throws(() => assertBoolean(1, 'test', 'flag'), (err) => err instanceof Error);
  assert.throws(() => assertBoolean('true', 'test', 'flag'), (err) => err instanceof Error);
  assert.throws(() => assertBoolean(null, 'test', 'flag'), (err) => err instanceof Error);
  assert.throws(() => assertBoolean(undefined, 'test', 'flag'), (err) => err instanceof Error);
});

// ---------------------------------------------------------------
// (j) assertNonEmptyString
// ---------------------------------------------------------------

run('assertNonEmptyString accepts non-empty strings', () => {
  assert.equal(assertNonEmptyString('hello', 'test', 'label'), 'hello');
  assert.equal(assertNonEmptyString(' ', 'test', 'label'), ' ');
});

run('assertNonEmptyString rejects empty string', () => {
  assert.throws(
    () => assertNonEmptyString('', 'test', 'label'),
    (err) => err instanceof Error && err.message.includes('must not be empty'),
  );
});

run('assertNonEmptyString rejects null', () => {
  assert.throws(
    () => assertNonEmptyString(null, 'test', 'label'),
    (err) => err instanceof Error && err.message.includes('must be a string'),
  );
});

run('assertNonEmptyString rejects numbers', () => {
  assert.throws(
    () => assertNonEmptyString(42, 'test', 'label'),
    (err) => err instanceof Error,
  );
});

run('assertNonEmptyString rejects undefined', () => {
  assert.throws(
    () => assertNonEmptyString(undefined, 'test', 'label'),
    (err) => err instanceof Error,
  );
});

// ---------------------------------------------------------------
// Extra: assertString
// ---------------------------------------------------------------

run('assertString accepts strings', () => {
  assert.equal(assertString('abc', 'test', 'name'), 'abc');
  assert.equal(assertString('', 'test', 'name'), '');
});

run('assertString rejects non-strings', () => {
  assert.throws(() => assertString(123, 'test', 'name'), (err) => err instanceof Error);
  assert.throws(() => assertString(null, 'test', 'name'), (err) => err instanceof Error);
  assert.throws(() => assertString(true, 'test', 'name'), (err) => err instanceof Error);
});

// ---------------------------------------------------------------
// Extra: assertIntegerInRange
// ---------------------------------------------------------------

run('assertIntegerInRange accepts valid integers', () => {
  assert.equal(assertIntegerInRange(0, 'test', 'val'), 0);
  assert.equal(assertIntegerInRange(100, 'test', 'val'), 100);
  assert.equal(assertIntegerInRange(5, 'test', 'val', { min: 0, max: 10 }), 5);
});

run('assertIntegerInRange rejects out-of-range', () => {
  assert.throws(
    () => assertIntegerInRange(-1, 'test', 'val'),
    (err) => err instanceof Error,
  );
  assert.throws(
    () => assertIntegerInRange(11, 'test', 'val', { min: 0, max: 10 }),
    (err) => err instanceof Error,
  );
});

run('assertIntegerInRange rejects floats', () => {
  assert.throws(
    () => assertIntegerInRange(1.5, 'test', 'val'),
    (err) => err instanceof Error,
  );
});

run('assertIntegerInRange rejects NaN and Infinity', () => {
  assert.throws(() => assertIntegerInRange(NaN, 'test', 'val'), (err) => err instanceof Error);
  assert.throws(() => assertIntegerInRange(Infinity, 'test', 'val'), (err) => err instanceof Error);
});

// ---------------------------------------------------------------
// Extra: assertOptionalIntegerInRange
// ---------------------------------------------------------------

run('assertOptionalIntegerInRange allows undefined', () => {
  assert.equal(assertOptionalIntegerInRange(undefined, 'test', 'val'), undefined);
});

run('assertOptionalIntegerInRange validates non-undefined', () => {
  assert.equal(assertOptionalIntegerInRange(5, 'test', 'val', { min: 0, max: 10 }), 5);
  assert.throws(
    () => assertOptionalIntegerInRange(1.5, 'test', 'val'),
    (err) => err instanceof Error,
  );
});

// ---------------------------------------------------------------
// Extra: exported constants
// ---------------------------------------------------------------

run('MAX_SAFE_U64 equals Number.MAX_SAFE_INTEGER', () => {
  assert.equal(MAX_SAFE_U64, Number.MAX_SAFE_INTEGER);
});

run('UINT32_MAX equals 0xFFFFFFFF', () => {
  assert.equal(UINT32_MAX, 0xFFFFFFFF);
});

// --- Report ---

console.log(`\n  ${passed} passed, ${failed} failed\n`);
if (failed > 0) {
  process.exit(1);
}
