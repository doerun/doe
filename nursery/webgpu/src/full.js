import * as full from './index.js';
import { createDoeNamespace } from './doe.js';

/**
 * Shared Doe API / Doe routines namespace for the full package surface.
 *
 * This exposes `await doe.requestDevice()` for the one-line Doe API entry,
 * `doe.bind(device)` when you already have a full device, `doe.buffers.*` and
 * `doe.compute.run(...)` / `doe.compute.compile(...)` for the `Doe API`
 * surface, and `doe.compute.once(...)` for `Doe routines`.
 *
 * The exported `doe` object here is the JS convenience surface over the Doe
 * runtime, not a separate runtime.
 *
 * This example shows the API in its basic form.
 *
 * ```js
 * import { doe } from "@simulatte/webgpu";
 *
 * const gpu = await doe.requestDevice();
 * ```
 *
 * - The Doe API and Doe routines shape is the same as `@simulatte/webgpu/compute`; the difference is that the underlying device here stays full-surface rather than compute-only.
 * - If you need explicit render, sampler, or surface APIs, keep the raw device from `requestDevice()` or access `gpu.device` after `doe.requestDevice()`.
 */
export const doe = createDoeNamespace({
  requestDevice: full.requestDevice,
});

export * from './index.js';

export default {
  ...full,
  doe,
};
