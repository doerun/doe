import {
  failValidation,
  destroyResource,
} from './resource-lifecycle.js';

const DEFAULT_CANVAS_PRESENT_MODE = 0x00000001;
const CANVAS_ALPHA_MODE_MAP = Object.freeze({
  opaque: 0x00000001,
  premultiplied: 0x00000002,
});

function assert_canvas_dimension(canvas, key) {
  const value = Number(canvas?.[key]);
  if (!Number.isFinite(value) || value <= 0) {
    failValidation(
      'GPUCanvasContext',
      `canvas.${key} must be a positive number for the native Metal canvas backend`,
    );
  }
  return Math.trunc(value);
}

function assert_backend_ready(addon) {
  if (process.platform !== 'darwin') {
    failValidation(
      'GPUCanvasContext',
      'native Metal canvas backend is only available on macOS',
    );
  }
  if (
    !addon
    || typeof addon.canvasSurfaceCreate !== 'function'
    || typeof addon.canvasSurfaceConfigure !== 'function'
    || typeof addon.canvasSurfaceGetCurrentTexture !== 'function'
    || typeof addon.canvasSurfacePresent !== 'function'
    || typeof addon.canvasSurfaceUnconfigure !== 'function'
    || typeof addon.canvasSurfaceRelease !== 'function'
    || typeof addon.textureRelease !== 'function'
  ) {
    failValidation(
      'GPUCanvasContext',
      'native Metal canvas backend is unavailable in the loaded addon/runtime',
    );
  }
}

function destroy_current_texture(entry, addon) {
  const texture = entry.currentTexture;
  if (!texture || texture._destroyed) {
    entry.currentTexture = null;
    entry.presentPending = false;
    return;
  }
  const release = typeof texture._nativeCanvasRelease === 'function'
    ? texture._nativeCanvasRelease
    : (native) => {
      if (native != null) {
        addon.textureRelease(native);
      }
    };
  destroyResource(texture, release);
  entry.currentTexture = null;
  entry.presentPending = false;
}

function createNativeMetalCanvasBackend({ addon } = {}) {
  const context_entries = new WeakMap();

  function get_context_entry(context) {
    let entry = context_entries.get(context);
    if (entry) {
      return entry;
    }
    entry = {
      surface: null,
      device: null,
      width: 0,
      height: 0,
      configuration: null,
      currentTexture: null,
      presentPending: false,
    };
    context_entries.set(context, entry);
    return entry;
  }

  function ensure_surface(context, configuration) {
    const entry = get_context_entry(context);
    if (entry.surface != null) {
      return entry;
    }
    entry.surface = addon.canvasSurfaceCreate(configuration.device?._instance);
    if (entry.surface == null) {
      failValidation('GPUCanvasContext.configure', 'failed to create native Metal surface');
    }
    return entry;
  }

  function ensure_supported_configuration(configuration) {
    if (configuration.colorSpace !== 'srgb') {
      failValidation(
        'GPUCanvasContext.configure',
        'native Metal canvas backend currently supports only colorSpace="srgb"',
      );
    }
    if (configuration.toneMapping?.mode !== 'standard') {
      failValidation(
        'GPUCanvasContext.configure',
        'native Metal canvas backend currently supports only toneMapping.mode="standard"',
      );
    }
  }

  function current_canvas_size(context) {
    return {
      width: assert_canvas_dimension(context.canvas, 'width'),
      height: assert_canvas_dimension(context.canvas, 'height'),
    };
  }

  return {
    canvasContextConfigure(context, configuration) {
      assert_backend_ready(addon);
      ensure_supported_configuration(configuration);

      const entry = ensure_surface(context, configuration);
      const { width, height } = current_canvas_size(context);
      if (entry.device?._nativeCanvasContexts instanceof Set && entry.device !== configuration.device) {
        entry.device._nativeCanvasContexts.delete(context);
      }
      destroy_current_texture(entry, addon);

      addon.canvasSurfaceConfigure(entry.surface, configuration.device._native, {
        width,
        height,
        format: configuration.format,
        usage: configuration.usage,
        viewFormats: Array.isArray(configuration.viewFormats) ? [...configuration.viewFormats] : [],
        alphaMode: CANVAS_ALPHA_MODE_MAP[configuration.alphaMode] ?? CANVAS_ALPHA_MODE_MAP.opaque,
        presentMode: DEFAULT_CANVAS_PRESENT_MODE,
      });

      entry.device = configuration.device;
      entry.width = width;
      entry.height = height;
      entry.configuration = {
        ...configuration,
        viewFormats: Array.isArray(configuration.viewFormats) ? [...configuration.viewFormats] : [],
      };
      if (!(configuration.device._nativeCanvasContexts instanceof Set)) {
        configuration.device._nativeCanvasContexts = new Set();
      }
      configuration.device._nativeCanvasContexts.add(context);
    },

    canvasContextGetCurrentTexture(context, configuration, fullClasses) {
      assert_backend_ready(addon);
      const entry = ensure_surface(context, configuration);
      const size = current_canvas_size(context);
      if (
        entry.configuration
        && (size.width !== entry.width || size.height !== entry.height)
      ) {
        this.canvasContextConfigure(context, entry.configuration);
      }
      if (entry.currentTexture && !entry.currentTexture._destroyed) {
        return entry.currentTexture;
      }

      const native_texture = addon.canvasSurfaceGetCurrentTexture(entry.surface);
      if (!native_texture) {
        failValidation('GPUCanvasContext.getCurrentTexture', 'native Metal surface returned no texture');
      }
      const texture = new fullClasses.DoeGPUTexture(native_texture, configuration.device, {
        width: entry.width,
        height: entry.height,
        depthOrArrayLayers: 1,
        mipLevelCount: 1,
        sampleCount: 1,
        dimension: '2d',
        format: configuration.format,
        usage: configuration.usage,
        viewFormats: entry.configuration?.viewFormats ?? [],
        externallyOwned: true,
      });
      texture._nativeCanvasRelease = (native) => {
        if (native != null) {
          addon.textureRelease(native);
        }
        if (entry.currentTexture === texture) {
          entry.currentTexture = null;
          entry.presentPending = false;
        }
      };
      entry.currentTexture = texture;
      entry.presentPending = true;
      return texture;
    },

    canvasContextUnconfigure(context) {
      assert_backend_ready(addon);
      const entry = get_context_entry(context);
      if (entry.device?._nativeCanvasContexts instanceof Set) {
        entry.device._nativeCanvasContexts.delete(context);
      }
      destroy_current_texture(entry, addon);
      if (entry.surface) {
        addon.canvasSurfaceUnconfigure(entry.surface);
        addon.canvasSurfaceRelease(entry.surface);
        entry.surface = null;
      }
      entry.width = 0;
      entry.height = 0;
      entry.device = null;
      entry.configuration = null;
      entry.presentPending = false;
    },

    queuePresentPendingCanvasContexts(queue) {
      assert_backend_ready(addon);
      const contexts = queue?._device?._nativeCanvasContexts;
      if (!(contexts instanceof Set) || contexts.size === 0) {
        return;
      }
      for (const context of [...contexts]) {
        const entry = context_entries.get(context);
        if (!entry || entry.device !== queue._device || !entry.presentPending || !entry.currentTexture) {
          continue;
        }
        addon.canvasSurfacePresent(entry.surface);
        destroy_current_texture(entry, addon);
      }
    },

    releaseCanvasContext(context) {
      if (!context_entries.has(context)) {
        return;
      }
      const entry = get_context_entry(context);
      if (entry.device?._nativeCanvasContexts instanceof Set) {
        entry.device._nativeCanvasContexts.delete(context);
      }
      destroy_current_texture(entry, addon);
      if (entry.surface) {
        addon.canvasSurfaceRelease(entry.surface);
      }
      entry.surface = null;
      entry.device = null;
      entry.configuration = null;
      entry.presentPending = false;
      context_entries.delete(context);
    },

    externalTextureDestroy() {},
  };
}

export {
  createNativeMetalCanvasBackend,
};
