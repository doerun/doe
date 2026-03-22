# Direct WebGPU examples

These examples use the raw package-owned WebGPU surface from
`@simulatte/webgpu`.

- `request-device.js`
  smallest possible surface check
- `compute-dispatch.js`
  one compute pass with automatic pipeline layout and explicit readback
- `explicit-bind-group.js`
  the same basic compute flow with explicit bind-group and pipeline layouts
- `spawn-compute-worker.js` + `worker-compute.js`
  dispatch compute work from a Node.js worker thread and reuse the device across
  messages
