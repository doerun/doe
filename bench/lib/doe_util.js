export function shouldRetryDoeReadback(provider, workload, err) {
  return provider === 'doe'
    && workload.domain === 'compute'
    && typeof err?.message === 'string'
    && err.message.startsWith('expected readback[');
}
