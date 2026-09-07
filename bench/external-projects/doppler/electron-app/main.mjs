import 'electron';
import { createHash } from 'node:crypto';
import { readFile, realpath, writeFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

const exportTool = process.env.DOE_DOPPLER_QUALIFICATION_EXPORT_TOOL;
if (!exportTool) {
  throw new Error('DOE_DOPPLER_QUALIFICATION_EXPORT_TOOL is required.');
}

const workloadArgsStart = process.argv.indexOf('--doppler-root');
if (workloadArgsStart < 0) {
  throw new Error('Electron qualification workload arguments are missing.');
}
process.argv = [process.argv[0], exportTool, ...process.argv.slice(workloadArgsStart)];

const wrapper = await import(pathToFileURL(process.env.DOPPLER_NODE_WEBGPU_MODULE).href);
const provider = wrapper.__doeHarnessProviderIdentity;
const nativePath = await realpath(provider.id === 'doe-gpu'
  ? provider.providerInfo.doeLibraryPath
  : resolve(dirname(provider.modulePath), 'dist', `${process.platform}-${process.arch}.dawn.node`));
const loaded = process.report.getReport().sharedObjects.includes(nativePath);
if (!loaded) throw new Error(`Selected provider library is not loaded: ${nativePath}`);
const nativeIdentity = {
  schemaVersion: 1,
  providerId: provider.id,
  library: { path: nativePath, sha256: createHash('sha256').update(await readFile(nativePath)).digest('hex') },
  loaded,
};
const outputDirectory = process.argv[process.argv.indexOf('--out-dir') + 1];
await writeFile(resolve(outputDirectory, 'native-identity.json'), `${JSON.stringify(nativeIdentity, null, 2)}\n`);

await import(pathToFileURL(exportTool).href);
