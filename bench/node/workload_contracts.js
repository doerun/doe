import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const REGISTRY_PATH = resolve(__dirname, '..', 'workload-registry.json');

let registry;
try {
  registry = JSON.parse(readFileSync(REGISTRY_PATH, 'utf8'));
} catch (err) {
  throw new Error(`Cannot load workload registry ${REGISTRY_PATH}: ${err.message}`);
}
const packageContracts = new Map();

for (const workload of registry.workloads ?? []) {
  for (const surface of workload.surfaces ?? []) {
    if (surface.surface !== 'node_package' && surface.surface !== 'bun_package') continue;
    for (const workloadId of surface.workloadIds ?? []) {
      const existing = packageContracts.get(workloadId);
      if (existing && existing.canonicalWorkloadId !== workload.canonicalId) {
        throw new Error(
          `package workload registry collision for ${workloadId}: `
          + `${existing.canonicalWorkloadId} vs ${workload.canonicalId}`
        );
      }
      packageContracts.set(workloadId, {
        id: workloadId,
        canonicalWorkloadId: workload.canonicalId,
        domain: workload.domain,
        description: workload.description,
      });
    }
  }
}

export function packageWorkloadContract(id, comparable) {
  const contract = packageContracts.get(id);
  if (!contract) {
    throw new Error(`missing package workload contract for ${id} in ${REGISTRY_PATH}`);
  }
  return {
    ...contract,
    comparable,
  };
}

export { REGISTRY_PATH };
