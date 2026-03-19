import {
  failValidation,
  initResource,
  assertObject,
  assertLiveResource,
  destroyResource,
} from './resource-lifecycle.js';

const CANVAS_ALPHA_MODES = Object.freeze({
  opaque: 'opaque',
  premultiplied: 'premultiplied',
});

const CANVAS_TONE_MAPPING_MODES = Object.freeze({
  standard: 'standard',
  extended: 'extended',
});

const CANVAS_COLOR_SPACES = Object.freeze({
  srgb: 'srgb',
  'display-p3': 'display-p3',
});

function normalizeOrigin2D(origin, path) {
  if (origin === undefined || origin === null) return { x: 0, y: 0 };
  if (Array.isArray(origin)) {
    return { x: origin[0] ?? 0, y: origin[1] ?? 0 };
  }
  const obj = assertObject(origin, path, 'origin');
  return { x: obj.x ?? 0, y: obj.y ?? 0 };
}

function normalizeCanvasConfiguration(config, path) {
  const device = assertLiveResource(config.device, path, 'GPUDevice');
  const format = config.format;
  if (!format || typeof format !== 'string') {
    failValidation(path, 'configuration.format is required');
  }
  const alphaMode = config.alphaMode ?? 'opaque';
  if (!(alphaMode in CANVAS_ALPHA_MODES)) {
    failValidation(path, `alphaMode must be one of: ${Object.keys(CANVAS_ALPHA_MODES).join(', ')}`);
  }
  const colorSpace = config.colorSpace ?? 'srgb';
  if (!(colorSpace in CANVAS_COLOR_SPACES)) {
    failValidation(path, `colorSpace must be one of: ${Object.keys(CANVAS_COLOR_SPACES).join(', ')}`);
  }
  const toneMappingMode = config.toneMapping?.mode ?? 'standard';
  if (!(toneMappingMode in CANVAS_TONE_MAPPING_MODES)) {
    failValidation(path, `toneMapping.mode must be one of: ${Object.keys(CANVAS_TONE_MAPPING_MODES).join(', ')}`);
  }
  return {
    device,
    format,
    usage: config.usage ?? 0x10, /* RENDER_ATTACHMENT */
    alphaMode,
    colorSpace,
    toneMapping: { mode: toneMappingMode },
    viewFormats: Array.isArray(config.viewFormats) ? [...config.viewFormats] : [],
  };
}

function createBrowserSurfaceClasses({ canvasBackend, fullClasses }) {
  if (typeof fullClasses.DoeGPU === 'function') {
    fullClasses.DoeGPU.prototype.getPreferredCanvasFormat = function getPreferredCanvasFormat() {
      return this._native?.getPreferredCanvasFormat?.() ?? 'bgra8unorm';
    };
  }

  class DoeGPUCanvasContext {
    constructor(canvas) {
      this._canvas = canvas;
      this._configuration = null;
      this._currentTexture = null;
      this.label = '';
      initResource(this, 'GPUCanvasContext');
    }

    get canvas() {
      return this._canvas;
    }

    configure(configuration) {
      const config = assertObject(configuration, 'GPUCanvasContext.configure', 'configuration');
      if (this._currentTexture && !this._currentTexture._destroyed) {
        destroyResource(this._currentTexture, (native) => native.destroy?.());
      }
      this._configuration = normalizeCanvasConfiguration(config, 'GPUCanvasContext.configure');
      this._currentTexture = null;
      canvasBackend.canvasContextConfigure(this, this._configuration);
    }

    getConfiguration() {
      if (!this._configuration) return null;
      const c = this._configuration;
      return {
        device: c.device,
        format: c.format,
        usage: c.usage,
        alphaMode: c.alphaMode,
        colorSpace: c.colorSpace,
        toneMapping: { mode: c.toneMapping.mode },
        viewFormats: [...c.viewFormats],
      };
    }

    getCurrentTexture() {
      if (!this._configuration) {
        failValidation('GPUCanvasContext.getCurrentTexture', 'context is not configured');
      }
      if (this._currentTexture && !this._currentTexture._destroyed) {
        destroyResource(this._currentTexture, (native) => native.destroy?.());
      }
      this._currentTexture = canvasBackend.canvasContextGetCurrentTexture(
        this, this._configuration, fullClasses,
      );
      return this._currentTexture;
    }

    unconfigure() {
      if (this._currentTexture && !this._currentTexture._destroyed) {
        destroyResource(this._currentTexture, (native) => native.destroy?.());
      }
      if (this._configuration) {
        canvasBackend.canvasContextUnconfigure(this);
      }
      this._configuration = null;
      this._currentTexture = null;
    }
  }

  class DoeGPUExternalTexture {
    constructor(native, owner) {
      this._native = native;
      this.label = '';
      this.expired = false;
      initResource(this, 'GPUExternalTexture', owner);
    }

    destroy() {
      destroyResource(this, (native) => canvasBackend.externalTextureDestroy(native));
      this.expired = true;
    }
  }

  return Object.assign(fullClasses, {
    DoeGPUCanvasContext,
    DoeGPUExternalTexture,
    normalizeOrigin2D,
  });
}

export {
  CANVAS_ALPHA_MODES,
  CANVAS_TONE_MAPPING_MODES,
  CANVAS_COLOR_SPACES,
  normalizeOrigin2D,
  normalizeCanvasConfiguration,
  createBrowserSurfaceClasses,
};
