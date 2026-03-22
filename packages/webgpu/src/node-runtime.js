if (!globalThis.__SIMULATTE_WEBGPU_DEPRECATION_WARNED) {
  globalThis.__SIMULATTE_WEBGPU_DEPRECATION_WARNED = true;
  console.warn(
    '[@simulatte/webgpu] This package is deprecated. Use "doe-gpu" instead:\n' +
    '  npm install doe-gpu\n' +
    '  import { gpu } from "doe-gpu";\n'
  );
}

export * from "./full.js";
export { default } from "./full.js";
