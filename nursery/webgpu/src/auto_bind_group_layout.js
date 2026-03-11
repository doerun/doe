export function inferAutoBindGroupLayouts(code, visibility) {
  const groups = new Map();
  const bindingPattern = /@group\((\d+)\)\s*@binding\((\d+)\)\s*var(?:<([^>]+)>)?\s+\w+\s*:\s*([^;]+);/g;

  for (const match of code.matchAll(bindingPattern)) {
    const group = Number(match[1]);
    const binding = Number(match[2]);
    const addressSpace = (match[3] ?? '').trim();
    const typeExpr = (match[4] ?? '').trim();
    let entry = null;

    if (addressSpace.startsWith('uniform')) {
      entry = { binding, visibility, buffer: { type: 'uniform' } };
    } else if (addressSpace.startsWith('storage')) {
      const readOnly = !addressSpace.includes('read_write');
      entry = { binding, visibility, buffer: { type: readOnly ? 'read-only-storage' : 'storage' } };
    } else if (typeExpr.startsWith('sampler')) {
      entry = { binding, visibility, sampler: {} };
    }

    if (!entry) continue;
    const entries = groups.get(group) ?? [];
    entries.push(entry);
    groups.set(group, entries);
  }

  for (const entries of groups.values()) {
    entries.sort((left, right) => left.binding - right.binding);
  }

  return groups;
}
