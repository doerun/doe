function scaffoldError() {
  const message =
    "[nursery/webgpu] is an internal placeholder only. " +
    "Use the canonical package implementation in nursery/webgpu-core (`@simulatte/webgpu`).";
  const err = new Error(message);
  err.code = "DOE_WEBGPU_NOT_READY";
  return err;
}

export const runtimeState = {
  tier: "doe-runtime",
  status: "scaffold",
};

export function createDoeRuntime() {
  throw scaffoldError();
}

export function runDawnVsDoeCompare() {
  throw scaffoldError();
}

export function providerInfo() {
  return {
    package: "@simulatte/webgpu-placeholder",
    status: "placeholder",
    note: "Canonical package identity is @simulatte/webgpu from nursery/webgpu-core.",
  };
}

export default {
  createDoeRuntime,
  runDawnVsDoeCompare,
  providerInfo,
  runtimeState,
};
