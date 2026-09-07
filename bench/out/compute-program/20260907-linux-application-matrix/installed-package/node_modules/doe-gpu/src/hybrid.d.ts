export interface HybridConfig {
  /** Doppler model ID (e.g., 'gemma3-270m') */
  localModel?: string;
  /** OpenAI-compatible API URL */
  cloudEndpoint?: string;
  /** API key for cloud endpoint */
  cloudApiKey?: string;
  /** Cloud model name (e.g., 'gpt-4o-mini') */
  cloudModel?: string;
  /** Routing mode */
  mode?: 'prefer-local' | 'prefer-cloud' | 'local-only' | 'cloud-only';
  /** Max time to wait for local model load in ms (default: 10000) */
  localTimeoutMs?: number;
  /** Max tokens for local generation before cloud takeover */
  maxLocalTokens?: number;
}

export interface HybridProvider {
  /** Stream tokens from local or cloud, returning an AsyncGenerator */
  generate(prompt: string): AsyncGenerator<string, void, unknown>;
  /** Collect all tokens into a single string */
  generateText(prompt: string): Promise<string>;
  /** Unload local model and release resources */
  dispose(): Promise<void>;
  /** Whether the local model is loaded and healthy */
  readonly localReady: boolean;
  /** Active routing mode */
  readonly mode: 'prefer-local' | 'prefer-cloud' | 'local-only' | 'cloud-only';
}

export function createHybridProvider(config?: HybridConfig): Promise<HybridProvider>;
