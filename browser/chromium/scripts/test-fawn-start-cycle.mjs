import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const page = readFileSync(new URL('../resources/fawn-start.html', import.meta.url), 'utf8');
const declarations = page.split('<script>')[1].split('(async () => {')[0];
const phase = vm.runInNewContext(`${declarations}; scenePhase`);
for (const [seconds, expected] of [
  [0, 0], [6, 0], [6.5, .5], [7, 1], [13, 1], [13.5, 1.5],
  [14, 2], [20, 2], [20.5, 2.5], [21, 0], [27.5, .5],
]) {
  assert.equal(phase(seconds), expected, `phase at ${seconds}s`);
}
assert.ok(phase(6.001) < .00001, 'blend starts with near-zero slope');
assert.ok(3 - phase(20.999) < .00001, 'wrap approaches the first field smoothly');
assert.ok(!page.includes('data-scene='), 'no separate scene controls');
console.log('Fawn cycle: hold, blend, wrap, and repeated intervals passed.');
