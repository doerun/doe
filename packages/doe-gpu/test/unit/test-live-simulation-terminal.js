import assert from 'node:assert/strict';
import { EventEmitter } from 'node:events';
import { PassThrough } from 'node:stream';
import { heatField, runLiveTerminal } from '../../examples/live-simulation/terminal.js';
import { POLICY, DEFAULT_SHADER, STATE_FORMAT } from '../../examples/live-simulation/program.js';
import { initialState } from '../../examples/live-simulation/reference.js';

const bytes = new Uint8Array(initialState().buffer);
const unaligned = new Uint8Array(bytes.length + 1);
unaligned.set(bytes, 1);
const rendered = heatField(unaligned.subarray(1));
assert.match(rendered, /Checked GPU output; relative scale \[0, 1\]/);
assert.equal(rendered.split('\n').length, POLICY.height + 1);
assert.equal(rendered.split('@').length, 2);
assert.match(heatField(null), /No accepted frame/);
assert.throws(() => heatField(bytes.subarray(1)), /extent/);
new DataView(unaligned.buffer).setFloat32(1, Number.NaN, true);
assert.throws(() => heatField(unaligned.subarray(1)), /non-finite/);

const input = new PassThrough();
const output = new PassThrough();
let transcript = '';
output.on('data', (chunk) => { transcript += chunk; });
const instances = [];
let beginOpening;
let delayOpening = null;
let rejectOpening = false;
const calls = [];
async function createSession(options) {
  if (rejectOpening) throw new Error('initialization rejected');
  if (delayOpening) { beginOpening(); await delayOpening; }
  const session = {
    events: new EventEmitter(), initialization: { preparationMs: 2 },
    shaderSource: options.code, output: bytes,
    status: { stateFormat: options.stateFormat, rate: options.rate, closed: false },
    setRate(rate) { session.status.rate = rate; },
    async propose(code, format) { calls.push(['propose', code, format]); return { status: 'reset-required' }; },
    async decideReset(id, approve) { calls.push(['reset', id, approve]); },
    async cancelEdit() { calls.push(['cancel']); },
    async close() { session.status.closed = true; calls.push(['close']); },
  };
  instances.push({ options, session });
  return session;
}

const terminal = await runLiveTerminal({ backend: 'vulkan', execution: 'webgpu', input, output, createSession });
try {
  assert.match(transcript, /preparation 2.000ms/);
  await terminal.execute('view');
  assert.match(transcript, /Checked GPU output/);
  await terminal.execute('rate 0.2');
  await terminal.execute('format replacement');
  await terminal.execute('approve 17');
  await terminal.execute('decline 18');
  await terminal.execute('cancel');
  assert.deepEqual(calls.slice(0, 4), [
    ['propose', DEFAULT_SHADER, 'replacement'], ['reset', 17, true], ['reset', 18, false], ['cancel'],
  ]);
  await assert.rejects(terminal.execute('reopen'), /close the current/);
  instances[0].session.shaderSource = `${DEFAULT_SHADER}\n// accepted`;
  instances[0].session.status.stateFormat = `${STATE_FORMAT}/accepted`;
  instances[0].session.events.emit('event', { kind: 'activated', editId: 9, preparationMs: 3, activationMs: 4, reset: false });
  instances[0].session.events.emit('event', { kind: 'failure', message: 'retained failure' });
  assert.match(transcript, /preparation 3.000ms; activation pause 4.000ms; state retained/);
  assert.match(transcript, /no recovery of failed GPU state is assumed/);
  await terminal.execute('close');

  rejectOpening = true;
  await assert.rejects(terminal.execute('reopen'), /initialization rejected/);
  rejectOpening = false;
  assert.equal(instances[0].session.events.listenerCount('event'), 0);
  await assert.rejects(terminal.execute('rate 0.1'), /not open/);
  await terminal.execute('reopen');
  assert.equal(instances[1].options.code, instances[0].session.shaderSource);
  assert.equal(instances[1].options.stateFormat, instances[0].session.status.stateFormat);
  assert.equal(instances[1].options.rate, 0.2);
  await terminal.execute('close');

  let releaseOpening;
  delayOpening = new Promise((resolve) => { releaseOpening = resolve; });
  const began = new Promise((resolve) => { beginOpening = resolve; });
  const reopen = terminal.execute('reopen');
  await began;
  const quit = terminal.close();
  assert.equal(terminal.close(), quit);
  releaseOpening();
  await reopen;
  await quit;
  await terminal.closed;
  assert(instances.every(({ session }) => session.status.closed));
  assert.equal(instances[2].session.events.listenerCount('event'), 0);
  await assert.rejects(terminal.execute('reopen'), /terminal is closing/);
} finally {
  await terminal.close();
  input.destroy();
  output.destroy();
}
console.log('ok: checked heat view, preparation, explicit reset routing, close/reopen, and cleanup during initialization');

const failingInput = new PassThrough();
const failingOutput = new PassThrough();
failingOutput.resume();
delayOpening = null;
const failing = await runLiveTerminal({ backend: 'vulkan', execution: 'webgpu',
  input: failingInput, output: failingOutput,
  async createSession(options) {
    const active = await createSession(options);
    active.close = async () => { throw new Error('cleanup rejected'); };
    return active;
  },
});
await Promise.all([
  assert.rejects(failing.closed, /cleanup rejected/),
  assert.rejects(failing.close(), /cleanup rejected/),
]);
failingInput.destroy();
failingOutput.destroy();
console.log('ok: cleanup failure rejects terminal completion instead of acknowledging success');
