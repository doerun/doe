export interface DoeCompilerArtifact {
  url: string | URL;
  sha256: string;
  byteLength: number;
}
export interface DoeWGSLResult {
  schemaVersion: 1;
  ok: true;
  wgsl: string;
  rewrites: number;
  diagnostics: unknown[];
  compileMs: number;
}
export interface DoeCompiler {
  readonly identity: { readonly label: 'Doe-assisted WebGPU'; readonly sha256: string };
  readonly initialization: {
    cacheReadMs: number; downloadMs: number; verifyMs: number; cacheWriteMs: number;
    instantiateMs: number; totalMs: number; bytesDownloaded: number;
    cacheStatus: string; sourceLimit: number;
  };
  compile(code: string, options: { optimize: boolean }): Promise<DoeWGSLResult>;
  close(reason?: Error): void;
}
export function createDoeCompiler(options: {
  artifact: DoeCompilerArtifact; cache?: boolean; timeoutMs?: number;
}): Promise<DoeCompiler>;
export function createDoeShaderAdapter<ShaderModule extends {
  getCompilationInfo(): Promise<{ messages: readonly { type: string }[] }>;
}>(options: {
  device: { createShaderModule(descriptor: { code: string; label?: string }): ShaderModule };
  compiler: DoeCompiler; optimize: boolean;
}): {
  readonly label: 'Doe-assisted WebGPU'; readonly executionOwner: 'browser';
  createShaderModule(descriptor: { code: string; label?: string }):
    Promise<DoeWGSLResult & { module: ShaderModule; workerRoundTripMs: number }>;
};
