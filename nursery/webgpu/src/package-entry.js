function scaffoldError() {
  const message =
    "[@doe/webgpu] package is currently scaffolded. " +
    "Use @doe/webgpu-core for runtime and CLI usage today.";
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
    package: "@doe/webgpu",
    status: "scaffold",
    note: "Full runtime entrypoints are not implemented yet.",
  };
}

export default {
  createDoeRuntime,
  runDawnVsDoeCompare,
  providerInfo,
  runtimeState,
};
