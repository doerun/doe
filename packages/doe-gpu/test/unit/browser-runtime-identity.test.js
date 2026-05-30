#!/usr/bin/env node

import assert from 'node:assert/strict';

import {
  createBrowserRuntimeIdentity,
} from '../../src/browser.js';

{
  const identity = createBrowserRuntimeIdentity({ gpu: null });
  assert.equal(identity.schemaVersion, 1);
  assert.equal(identity.artifactKind, 'browser_runtime_identity');
  assert.equal(identity.surface, 'doe-gpu/browser');
  assert.equal(identity.evidenceSource, 'browser_wrapper_probe');
  assert.equal(identity.selectedRuntime, 'browser_navigator_gpu');
  assert.equal(identity.executionOwner, 'browser');
  assert.equal(identity.doeRuntimeActive, false);
  assert.equal(identity.webgpuAvailable, false);
  assert.equal(identity.runtimeSelection, null);
  assert.equal(identity.provider.module, 'doe-gpu/browser');
}

{
  const runtimeSelection = {
    selectedRuntime: 'doe',
    fallbackApplied: false,
    fallbackReasonCode: '',
    hiddenFallbackAllowed: false,
    selectorVersion: 'browser-runtime-selector-v1',
  };
  const identity = createBrowserRuntimeIdentity({
    gpu: {},
    runtimeSelection,
  });
  assert.equal(identity.evidenceSource, 'runtime_selection_artifact');
  assert.equal(identity.selectedRuntime, 'doe');
  assert.equal(identity.executionOwner, 'chromium_runtime_selector');
  assert.equal(identity.doeRuntimeActive, true);
  assert.equal(identity.webgpuAvailable, true);
  assert.equal(identity.runtimeSelection, runtimeSelection);
}

{
  const identity = createBrowserRuntimeIdentity({
    gpu: {},
    runtimeSelection: {
      selectedRuntime: 'doe',
      fallbackApplied: true,
      fallbackReasonCode: 'runtime_artifact_missing',
      hiddenFallbackAllowed: false,
    },
  });
  assert.equal(identity.doeRuntimeActive, false);
}

{
  const identity = createBrowserRuntimeIdentity({
    gpu: {},
    runtimeSelection: {
      selectedRuntime: 'doe',
      fallbackApplied: false,
      fallbackReasonCode: '',
      hiddenFallbackAllowed: true,
    },
  });
  assert.equal(identity.doeRuntimeActive, false);
}

{
  const identity = createBrowserRuntimeIdentity({
    gpu: {},
    runtimeSelection: {
      selectedRuntime: 'doe',
      fallbackApplied: false,
    },
  });
  assert.equal(identity.doeRuntimeActive, false);
}

console.log('browser-runtime-identity.test: ok');
