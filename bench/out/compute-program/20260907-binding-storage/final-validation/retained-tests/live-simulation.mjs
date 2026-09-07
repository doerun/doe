import assert from 'node:assert/strict';
import { createLiveSimulation } from 'file:///home/x/deco/doe/bench/out/compute-program/20260907-dispatch-copy-applications/installed-package/node_modules/doe-gpu/examples/live-simulation/session.js';
import { POLICY, DEFAULT_SHADER, STATE_FORMAT } from 'file:///home/x/deco/doe/bench/out/compute-program/20260907-dispatch-copy-applications/installed-package/node_modules/doe-gpu/examples/live-simulation/program.js';

const backend = process.platform === 'darwin' ? 'metal' : 'vulkan';
const execution = process.env.DOE_LIVE_EXECUTION ?? (backend === 'vulkan' ? 'gpu-recorded' : 'native-recorded');
const PROLONGED_FRAMES = 4096;
const SAMPLE_WINDOW_FRAMES = 256;

function frames(session, count) {
  return new Promise((resolve, reject) => {
    const target = session.status.iteration + count;
    let timer;
    function armDeadline() {
      clearTimeout(timer);
      timer = setTimeout(() => finish(new Error('simulation did not advance within its configured deadline')), POLICY.requestTimeoutMs);
    }
    function finish(error) {
      clearTimeout(timer);
      session.events.off('frame', frame);
      session.events.off('failure', failure);
      if (error) reject(error); else resolve();
    }
    function frame({ iteration }) { if (iteration >= target) finish(); else armDeadline(); }
    function failure({ message }) { finish(new Error(message)); }
    session.events.on('frame', frame);
    session.events.on('failure', failure);
    armDeadline();
  });
}

const session = await createLiveSimulation({ backend, execution });
const checks = [];
const activations = [];
session.events.on('checked', (value) => checks.push(value));
session.events.on('activated', (value) => activations.push(value));
try {
  await frames(session, 3);
  const originalIteration = session.status.iteration;
  assert.equal((await session.propose('invalid WGSL')).status, 'rejected');
  await frames(session, 2);
  assert(session.status.iteration > originalIteration);
  console.log('ok: invalid shader leaves the running state usable');

  const wrong = DEFAULT_SHADER.replace('next[i] = state[i]', 'next[i] = 9.0 + state[i]');
  const rejected = await session.propose(wrong);
  assert.equal(rejected.status, 'rejected');
  assert.match(rejected.message, /independent heat reference/);
  await frames(session, 2);
  console.log('ok: independent acceptance rejects compiling but incorrect edits');

  const valid = `${DEFAULT_SHADER}\n// accepted equivalent edit\n`;
  const obsolete = session.propose(valid);
  const newest = session.propose(`${valid}// newest edit\n`);
  assert.equal((await obsolete).status, 'cancelled');
  assert.equal((await newest).status, 'activated');
  assert(checks.at(-1).framesDuringPreflight > 0);
  assert.equal(activations.at(-1).reset, false);
  console.log('ok: obsolete edits cancel while the simulation advances during preflight');

  session.setRate(POLICY.maximumRate);
  await frames(session, 3);
  assert.equal(session.status.lastFrame.rate, POLICY.maximumRate);
  const reset = await session.propose(valid, `${STATE_FORMAT}/new-interpretation`);
  assert.equal(reset.status, 'reset-required');
  assert.equal(session.status.paused, true);
  await assert.rejects(session.decideReset(reset.editId, 'false'), /explicit boolean/);
  await assert.rejects(session.decideReset(reset.editId + 1, true), /stale/);
  assert.equal((await session.decideReset(reset.editId, false)).status, 'declined');
  await frames(session, 2);
  assert.equal(session.status.stateFormat, STATE_FORMAT);
  console.log('ok: stale and declined reset decisions preserve the previous state');

  const approved = await session.propose(valid, `${STATE_FORMAT}/new-interpretation`);
  assert.equal((await session.decideReset(approved.editId, true)).reset, true);
  await frames(session, 3);
  assert.equal(session.status.stateFormat, `${STATE_FORMAT}/new-interpretation`);
  await assert.rejects(session.decideReset(approved.editId, true), /stale/);
  console.log('ok: exact reset approval initializes and checks the replacement state');

  if (process.argv.includes('--prolonged')) {
    let count = 0;
    let maximumError = 0;
    let maximumResidentBytes = 0;
    const started = performance.now();
    const observe = (frame) => {
      count += 1;
      maximumError = Math.max(maximumError, frame.maximumError);
      maximumResidentBytes = Math.max(maximumResidentBytes, frame.residentBytes);
      if (count % SAMPLE_WINDOW_FRAMES === 0) {
        console.log(`sample: frames=${count} elapsedMs=${performance.now() - started} workerRssBytes=${frame.residentBytes} maximumError=${maximumError}`);
      }
    };
    session.events.on('frame', observe);
    try { await frames(session, PROLONGED_FRAMES); }
    finally { session.events.off('frame', observe); }
    assert(count >= PROLONGED_FRAMES);
    console.log(`ok: prolonged independently checked simulation frames=${count} sampledMaximumWorkerRssBytes=${maximumResidentBytes}`);
  }

  const closingEdit = session.propose(valid);
  const closing = session.close();
  assert.equal(session.close(), closing);
  await closing;
  assert.equal((await closingEdit).status, 'cancelled');
  console.log('ok: closing cancels candidate work and releases the live worker');
} finally {
  await session.close();
}

const reopened = await createLiveSimulation({ backend, execution });
try {
  await frames(reopened, 3);
  console.log('ok: a closed workspace reopens with independently checked initial state');
} finally { await reopened.close(); }
