export function parseRunnerLines(stdout) {
  const text = stdout.trim();
  if (!text) return [];
  return text.split('\n').map((line) => JSON.parse(line));
}

export function selectedWorkloads(workloads, workloadFilter) {
  if (!workloadFilter) return workloads;
  return workloads.filter((w) => w.id === workloadFilter || w.domain === workloadFilter);
}
