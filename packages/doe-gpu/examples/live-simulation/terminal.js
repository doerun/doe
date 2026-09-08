// Presentation and reopening belong to the example, not the native runtime.
import { readFileSync, statSync, writeFileSync } from 'node:fs';
import { createInterface } from 'node:readline';
import { createLiveSimulation } from './session.js';
import { DEFAULT_SHADER, POLICY, STATE_FORMAT } from './program.js';

const HEAT_LEVELS = ' .:-=+*#%@';
const COMMANDS = 'Commands: view | edit path.wgsl | rate value | format state-format | approve id | decline id | cancel | save path.wgsl | status | close | reopen | quit';

function heatField(bytes) {
  if (!bytes) return 'No accepted frame yet.';
  if (bytes.byteLength !== POLICY.width * POLICY.height * Float32Array.BYTES_PER_ELEMENT) {
    throw new Error('heat view: output extent differs from the configured field');
  }
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const values = Array.from({ length: POLICY.width * POLICY.height }, (_, index) =>
    view.getFloat32(index * Float32Array.BYTES_PER_ELEMENT, true));
  if (values.some((value) => !Number.isFinite(value))) throw new Error('heat view: non-finite output');
  const minimum = Math.min(...values);
  const maximum = Math.max(...values);
  const range = maximum - minimum;
  const rows = Array.from({ length: POLICY.height }, (_, row) =>
    values.slice(row * POLICY.width, (row + 1) * POLICY.width).map((value) => {
      const level = range === 0 ? 0 : Math.round((value - minimum) / range * (HEAT_LEVELS.length - 1));
      return HEAT_LEVELS[level];
    }).join(''));
  return [`Checked GPU output; relative scale [${minimum}, ${maximum}]`, ...rows].join('\n');
}

async function runLiveTerminal({ backend, execution, input = process.stdin, output = process.stdout,
  createSession = createLiveSimulation }) {
  let session;
  let opening;
  let closing;
  let stopping;
  let saved = { code: DEFAULT_SHADER, stateFormat: STATE_FORMAT, rate: POLICY.rate };
  const write = (message) => output.write(`${message}\n`);
  let finish;
  let fail;
  const closed = new Promise((resolve, reject) => { finish = resolve; fail = reject; });

  function event(value) {
    switch (value.kind) {
      case 'frame':
        if (value.iteration % POLICY.statusEveryFrames === 0) {
          write(`iteration ${value.iteration}; rate ${value.rate}; checked operation ${value.operationMs.toFixed(3)}ms; maximum error ${value.maximumError}`);
        }
        break;
      case 'activated':
        write(`edit ${value.editId} activated; preparation ${value.preparationMs.toFixed(3)}ms; activation pause ${value.activationMs.toFixed(3)}ms; state ${value.reset ? 'reset' : 'retained'}`);
        break;
      case 'checked':
        write(`edit ${value.editId} checked; preflight ${value.preflightMs.toFixed(3)}ms; simulation advanced ${value.framesDuringPreflight} frames during checks`);
        break;
      case 'reset-required':
        write(`edit ${value.editId} would reset state; paused. Enter approve ${value.editId} or decline ${value.editId}.`);
        break;
      case 'failure':
        write(`simulation stopped: ${value.message}. Use close, then reopen to start fresh state; no recovery of failed GPU state is assumed.`);
        break;
      default:
        write(`${value.kind}${value.editId ? ` edit ${value.editId}` : ''}${value.inputKind ? `: ${value.inputKind}, rate ${value.rate}` : ''}${value.message ? `: ${value.message}` : ''}`);
    }
  }

  function openSession() {
    if (stopping || session || opening || closing) throw new Error('close the current simulation before reopening');
    write('Preparing the simulation; reopening initializes fresh state with the last accepted shader, format, and rate.');
    opening = (async () => {
      session = await createSession({ backend, execution, ...saved });
      session.events.on('event', event);
      write(`Running ${POLICY.width}x${POLICY.height} heat on ${backend}/${execution}; preparation ${session.initialization.preparationMs.toFixed(3)}ms.`);
    })().finally(() => { opening = null; });
    return opening;
  }

  function closeSession() {
    if (closing) return closing;
    closing = (async () => {
      // Initialization owns a bounded worker request. Wait for its cleanup before
      // allowing another session; closing never abandons a newly created worker.
      if (opening) await opening.catch(() => {});
      if (!session) return;
      const active = session;
      await active.close();
      saved = { code: active.shaderSource, stateFormat: active.status.stateFormat, rate: active.status.rate };
      active.events.off('event', event);
      session = null;
      write('Simulation closed; worker cleanup complete. Enter reopen to initialize fresh state.');
    })().finally(() => { closing = null; });
    return closing;
  }

  function activeSession() {
    if (!session || opening || closing || stopping) throw new Error('simulation is not open; use reopen after cleanup completes');
    return session;
  }

  async function execute(line) {
    if (stopping) throw new Error('terminal is closing');
    const [command, ...words] = line.trim().split(/\s+/);
    const argument = words.join(' ');
    switch (command) {
      case 'view': {
        const active = activeSession();
        write(`Snapshot iteration ${active.status.lastFrame?.iteration ?? 'none'}; ${active.status.failed ? 'simulation failed' : active.status.paused ? 'paused' : 'running'}`);
        write(heatField(active.output));
        break;
      }
      case 'edit': {
        const active = activeSession();
        if (statSync(argument).size > POLICY.maximumShaderBytes) throw new Error('shader exceeds configured size limit');
        return active.propose(readFileSync(argument, 'utf8'));
      }
      case 'format': { const active = activeSession(); return active.propose(active.shaderSource, argument); }
      case 'rate': activeSession().setRate(Number(argument)); write(`Next iteration rate: ${argument}`); break;
      case 'approve': return activeSession().decideReset(Number(argument), true);
      case 'decline': return activeSession().decideReset(Number(argument), false);
      case 'cancel': await activeSession().cancelEdit(); write('Candidate cancelled; active submitted work is not preempted.'); break;
      case 'save': writeFileSync(argument, session?.shaderSource ?? saved.code, { flag: 'wx' }); break;
      case 'status': write(JSON.stringify(session?.status ?? { closed: true, ...saved }, null, 2)); break;
      case 'close': return closeSession();
      case 'reopen': return openSession();
      case 'quit': return close();
      default: write(COMMANDS);
    }
  }

  await openSession();
  const lines = createInterface({ input, output, terminal: Boolean(input.isTTY && output.isTTY) });
  function close() {
    if (stopping) return stopping;
    // Defer line closure until stopping is assigned, because close emits inline.
    stopping = Promise.resolve().then(async () => {
      lines.close();
      try { await closeSession(); finish(); }
      catch (error) { fail(error); throw error; }
    });
    return stopping;
  }
  lines.on('line', (line) => { void execute(line).catch((error) => write(`Error: ${error.message}`)); });
  lines.on('close', () => { void close().catch((error) => write(`Cleanup failed: ${error.message}`)); });
  write(COMMANDS);
  return { execute, close, closed };
}

export { heatField, runLiveTerminal };
