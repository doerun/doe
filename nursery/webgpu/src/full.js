import * as full from './index.js';
import { createDoeNamespace } from './doe.js';

/**
 * Shared Doe API namespace for the full package surface.
 *
 * Surface: Doe API on `@simulatte/webgpu`.
 * Input: Called through `doe.requestDevice(...)` or `doe.bind(device)`.
 * Returns: A bound `gpu` helper object over a full raw device.
 *
 * This is the JS convenience surface over the full package. Both entry points
 * return the same bound `gpu` object, with `gpu.buffer.*`, `gpu.kernel.*`,
 * and `gpu.compute.once(...)`, while still leaving the underlying raw device
 * reachable as `gpu.device`.
 *
 * This example shows the API in its basic form.
 *
 * ```js
 * import { doe } from "@simulatte/webgpu";
 *
 * const gpu = await doe.requestDevice();
 * ```
 *
 * - The Doe helper shape matches `@simulatte/webgpu/compute`; the difference is the raw device underneath.
 * - If you need explicit render, sampler, or surface APIs, use `gpu.device`.
 * - See the package `requestDevice()` export when you want the raw full device without Doe helpers.
 */
export const doe = createDoeNamespace({
  requestDevice: full.requestDevice,
});

export * from './index.js';

export default {
  ...full,
  doe,
};
