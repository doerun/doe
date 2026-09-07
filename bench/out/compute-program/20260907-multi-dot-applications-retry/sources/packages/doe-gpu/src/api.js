// doe-gpu/api - provider-neutral Doe API layer.

import doe, { createDoeNamespace } from './vendor/doe-namespace.js';

export const createGpuNamespace = createDoeNamespace;
export const gpu = doe;

export { createDoeNamespace, doe };

export default doe;
