export function fmt(ms) {
  if (ms == null) return '-';
  if (ms < 0.01) return (ms * 1000).toFixed(1) + 'us';
  return ms.toFixed(3) + 'ms';
}
