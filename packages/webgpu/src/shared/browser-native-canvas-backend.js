import {
  failValidation,
} from './resource-lifecycle.js';

function default_context_factory(canvas) {
  if (!canvas || typeof canvas.getContext !== 'function') {
    failValidation(
      'GPUCanvasContext',
      'canvas must provide getContext("webgpu") for the native browser canvas backend',
    );
  }
  return canvas.getContext('webgpu');
}

function texture_meta(native_texture) {
  return {
    width: native_texture?.width ?? 1,
    height: native_texture?.height ?? 1,
    depthOrArrayLayers: native_texture?.depthOrArrayLayers ?? 1,
    mipLevelCount: native_texture?.mipLevelCount ?? 1,
    sampleCount: native_texture?.sampleCount ?? 1,
    dimension: native_texture?.dimension ?? '2d',
    format: native_texture?.format ?? 'bgra8unorm',
    usage: native_texture?.usage ?? 0,
  };
}

function createNativeBrowserCanvasBackend({ contextFactory = default_context_factory } = {}) {
  const native_contexts = new WeakMap();

  function resolve_native_context(context) {
    let native_context = native_contexts.get(context);
    if (native_context) {
      return native_context;
    }
    native_context = contextFactory(context.canvas, context);
    if (!native_context || typeof native_context.configure !== 'function') {
      failValidation(
        'GPUCanvasContext',
        'native browser canvas backend requires a GPUCanvasContext-compatible object',
      );
    }
    native_contexts.set(context, native_context);
    return native_context;
  }

  return {
    canvasContextConfigure(context, configuration) {
      const native_context = resolve_native_context(context);
      native_context.configure({
        ...configuration,
        device: configuration.device?._native ?? configuration.device,
        viewFormats: Array.isArray(configuration.viewFormats) ? [...configuration.viewFormats] : [],
      });
    },

    canvasContextGetCurrentTexture(context, configuration, fullClasses) {
      const native_context = resolve_native_context(context);
      const native_texture = native_context.getCurrentTexture();
      if (!native_texture) {
        failValidation('GPUCanvasContext.getCurrentTexture', 'native browser canvas context returned no texture');
      }
      return new fullClasses.DoeGPUTexture(
        native_texture,
        configuration.device,
        texture_meta(native_texture),
      );
    },

    canvasContextUnconfigure(context) {
      const native_context = resolve_native_context(context);
      if (typeof native_context.unconfigure === 'function') {
        native_context.unconfigure();
      }
    },

    externalTextureDestroy(native) {
      if (native && typeof native.destroy === 'function') {
        native.destroy();
      }
    },

    deviceImportExternalTexture(device, native, descriptor, classes) {
      if (!native || typeof native.importExternalTexture !== 'function') {
        failValidation(
          'GPUDevice.importExternalTexture',
          'native browser device does not support importExternalTexture',
        );
      }
      const native_external_texture = native.importExternalTexture(descriptor);
      if (!native_external_texture) {
        failValidation('GPUDevice.importExternalTexture', 'native browser device failed to import external texture');
      }
      return new classes.DoeGPUExternalTexture(native_external_texture, device);
    },

    queueCopyExternalImageToTexture(_queue, native, source, destination, copySize) {
      if (!native || typeof native.copyExternalImageToTexture !== 'function') {
        failValidation(
          'GPUQueue.copyExternalImageToTexture',
          'native browser queue does not support copyExternalImageToTexture',
        );
      }
      return native.copyExternalImageToTexture(
        source,
        {
          ...destination,
          texture: destination.texture?._native ?? destination.texture,
        },
        copySize,
      );
    },
  };
}

export {
  createNativeBrowserCanvasBackend,
};
