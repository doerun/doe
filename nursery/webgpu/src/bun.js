import * as full from "./bun-ffi.js";
import { createDoeNamespace } from "./doe.js";

export const doe = createDoeNamespace({
  requestDevice: full.requestDevice,
});

export * from "./bun-ffi.js";

export default {
  ...full,
  doe,
};
