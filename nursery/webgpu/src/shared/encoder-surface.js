import {
  UINT32_MAX,
  failValidation,
  initResource,
  assertObject,
  assertIntegerInRange,
  assertLiveResource,
} from './resource-lifecycle.js';

function createEncoderClasses(backend) {
  let classes = null;

  class DoeGPUComputePassEncoder {
    constructor(state, encoder) {
      this._encoder = encoder;
      initResource(this, 'GPUComputePassEncoder', encoder);
      backend.computePassInit(this, state);
    }

    _assertOpen(path) {
      if (typeof backend.computePassAssertOpen === 'function') {
        backend.computePassAssertOpen(this, path);
      }
    }

    setPipeline(pipeline) {
      this._assertOpen('GPUComputePassEncoder.setPipeline');
      backend.computePassSetPipeline(
        this,
        assertLiveResource(pipeline, 'GPUComputePassEncoder.setPipeline', 'GPUComputePipeline'),
      );
    }

    setBindGroup(index, bindGroup) {
      this._assertOpen('GPUComputePassEncoder.setBindGroup');
      assertIntegerInRange(index, 'GPUComputePassEncoder.setBindGroup', 'index', { min: 0, max: UINT32_MAX });
      backend.computePassSetBindGroup(
        this,
        index,
        assertLiveResource(bindGroup, 'GPUComputePassEncoder.setBindGroup', 'GPUBindGroup'),
      );
    }

    dispatchWorkgroups(x, y = 1, z = 1) {
      this._assertOpen('GPUComputePassEncoder.dispatchWorkgroups');
      assertIntegerInRange(x, 'GPUComputePassEncoder.dispatchWorkgroups', 'x', { min: 0, max: UINT32_MAX });
      assertIntegerInRange(y, 'GPUComputePassEncoder.dispatchWorkgroups', 'y', { min: 0, max: UINT32_MAX });
      assertIntegerInRange(z, 'GPUComputePassEncoder.dispatchWorkgroups', 'z', { min: 0, max: UINT32_MAX });
      backend.computePassDispatchWorkgroups(this, x, y, z);
    }

    dispatchWorkgroupsIndirect(indirectBuffer, indirectOffset = 0) {
      this._assertOpen('GPUComputePassEncoder.dispatchWorkgroupsIndirect');
      assertIntegerInRange(indirectOffset, 'GPUComputePassEncoder.dispatchWorkgroupsIndirect', 'indirectOffset', { min: 0 });
      backend.computePassDispatchWorkgroupsIndirect(
        this,
        assertLiveResource(indirectBuffer, 'GPUComputePassEncoder.dispatchWorkgroupsIndirect', 'GPUBuffer'),
        indirectOffset,
      );
    }

    end() {
      this._assertOpen('GPUComputePassEncoder.end');
      backend.computePassEnd(this);
    }
  }

  class DoeGPURenderPassEncoder {
    constructor(state, encoder) {
      this._encoder = encoder;
      initResource(this, 'GPURenderPassEncoder', encoder);
      backend.renderPassInit(this, state);
    }

    _assertOpen(path) {
      if (typeof backend.renderPassAssertOpen === 'function') {
        backend.renderPassAssertOpen(this, path);
      }
    }

    setPipeline(pipeline) {
      this._assertOpen('GPURenderPassEncoder.setPipeline');
      backend.renderPassSetPipeline(
        this,
        assertLiveResource(pipeline, 'GPURenderPassEncoder.setPipeline', 'GPURenderPipeline'),
      );
    }

    setBindGroup(index, bindGroup) {
      this._assertOpen('GPURenderPassEncoder.setBindGroup');
      assertIntegerInRange(index, 'GPURenderPassEncoder.setBindGroup', 'index', { min: 0, max: UINT32_MAX });
      backend.renderPassSetBindGroup(
        this,
        index,
        assertLiveResource(bindGroup, 'GPURenderPassEncoder.setBindGroup', 'GPUBindGroup'),
      );
    }

    setVertexBuffer(slot, buffer, offset = 0, size) {
      this._assertOpen('GPURenderPassEncoder.setVertexBuffer');
      assertIntegerInRange(slot, 'GPURenderPassEncoder.setVertexBuffer', 'slot', { min: 0, max: UINT32_MAX });
      assertIntegerInRange(offset, 'GPURenderPassEncoder.setVertexBuffer', 'offset', { min: 0 });
      if (size !== undefined) {
        assertIntegerInRange(size, 'GPURenderPassEncoder.setVertexBuffer', 'size', { min: 0 });
      }
      backend.renderPassSetVertexBuffer(
        this,
        slot,
        assertLiveResource(buffer, 'GPURenderPassEncoder.setVertexBuffer', 'GPUBuffer'),
        offset,
        size,
      );
    }

    setIndexBuffer(buffer, format, offset = 0, size) {
      this._assertOpen('GPURenderPassEncoder.setIndexBuffer');
      assertIntegerInRange(offset, 'GPURenderPassEncoder.setIndexBuffer', 'offset', { min: 0 });
      if (size !== undefined) {
        assertIntegerInRange(size, 'GPURenderPassEncoder.setIndexBuffer', 'size', { min: 0 });
      }
      backend.renderPassSetIndexBuffer(
        this,
        assertLiveResource(buffer, 'GPURenderPassEncoder.setIndexBuffer', 'GPUBuffer'),
        format,
        offset,
        size,
      );
    }

    draw(vertexCount, instanceCount = 1, firstVertex = 0, firstInstance = 0) {
      this._assertOpen('GPURenderPassEncoder.draw');
      assertIntegerInRange(vertexCount, 'GPURenderPassEncoder.draw', 'vertexCount', { min: 0, max: UINT32_MAX });
      assertIntegerInRange(instanceCount, 'GPURenderPassEncoder.draw', 'instanceCount', { min: 0, max: UINT32_MAX });
      assertIntegerInRange(firstVertex, 'GPURenderPassEncoder.draw', 'firstVertex', { min: 0, max: UINT32_MAX });
      assertIntegerInRange(firstInstance, 'GPURenderPassEncoder.draw', 'firstInstance', { min: 0, max: UINT32_MAX });
      backend.renderPassDraw(this, vertexCount, instanceCount, firstVertex, firstInstance);
    }

    drawIndexed(indexCount, instanceCount = 1, firstIndex = 0, baseVertex = 0, firstInstance = 0) {
      this._assertOpen('GPURenderPassEncoder.drawIndexed');
      assertIntegerInRange(indexCount, 'GPURenderPassEncoder.drawIndexed', 'indexCount', { min: 0, max: UINT32_MAX });
      assertIntegerInRange(instanceCount, 'GPURenderPassEncoder.drawIndexed', 'instanceCount', { min: 0, max: UINT32_MAX });
      assertIntegerInRange(firstIndex, 'GPURenderPassEncoder.drawIndexed', 'firstIndex', { min: 0, max: UINT32_MAX });
      assertIntegerInRange(firstInstance, 'GPURenderPassEncoder.drawIndexed', 'firstInstance', { min: 0, max: UINT32_MAX });
      backend.renderPassDrawIndexed(this, indexCount, instanceCount, firstIndex, baseVertex, firstInstance);
    }

    drawIndirect(indirectBuffer, indirectOffset = 0) {
      this._assertOpen('GPURenderPassEncoder.drawIndirect');
      assertIntegerInRange(indirectOffset, 'GPURenderPassEncoder.drawIndirect', 'indirectOffset', { min: 0 });
      backend.renderPassDrawIndirect(
        this,
        assertLiveResource(indirectBuffer, 'GPURenderPassEncoder.drawIndirect', 'GPUBuffer'),
        indirectOffset,
      );
    }

    drawIndexedIndirect(indirectBuffer, indirectOffset = 0) {
      this._assertOpen('GPURenderPassEncoder.drawIndexedIndirect');
      assertIntegerInRange(indirectOffset, 'GPURenderPassEncoder.drawIndexedIndirect', 'indirectOffset', { min: 0 });
      backend.renderPassDrawIndexedIndirect(
        this,
        assertLiveResource(indirectBuffer, 'GPURenderPassEncoder.drawIndexedIndirect', 'GPUBuffer'),
        indirectOffset,
      );
    }

    end() {
      this._assertOpen('GPURenderPassEncoder.end');
      backend.renderPassEnd(this);
    }
  }

  class DoeGPUCommandEncoder {
    constructor(state, device) {
      this._device = device;
      initResource(this, 'GPUCommandEncoder', device);
      backend.commandEncoderInit(this, state);
    }

    _assertOpen(path) {
      assertLiveResource(this._device, path, 'GPUDevice');
      if (typeof backend.commandEncoderAssertOpen === 'function') {
        backend.commandEncoderAssertOpen(this, path);
      }
    }

    beginComputePass(descriptor) {
      this._assertOpen('GPUCommandEncoder.beginComputePass');
      return backend.commandEncoderBeginComputePass(this, descriptor, classes);
    }

    beginRenderPass(descriptor) {
      this._assertOpen('GPUCommandEncoder.beginRenderPass');
      const passDescriptor = assertObject(descriptor, 'GPUCommandEncoder.beginRenderPass', 'descriptor');
      return backend.commandEncoderBeginRenderPass(this, passDescriptor, classes);
    }

    copyBufferToBuffer(src, srcOffset, dst, dstOffset, size) {
      this._assertOpen('GPUCommandEncoder.copyBufferToBuffer');
      assertIntegerInRange(srcOffset, 'GPUCommandEncoder.copyBufferToBuffer', 'srcOffset', { min: 0 });
      assertIntegerInRange(dstOffset, 'GPUCommandEncoder.copyBufferToBuffer', 'dstOffset', { min: 0 });
      assertIntegerInRange(size, 'GPUCommandEncoder.copyBufferToBuffer', 'size', { min: 1 });
      backend.commandEncoderCopyBufferToBuffer(
        this,
        assertLiveResource(src, 'GPUCommandEncoder.copyBufferToBuffer', 'GPUBuffer'),
        srcOffset,
        assertLiveResource(dst, 'GPUCommandEncoder.copyBufferToBuffer', 'GPUBuffer'),
        dstOffset,
        size,
      );
    }

    copyTextureToBuffer(source, destination, copySize) {
      this._assertOpen('GPUCommandEncoder.copyTextureToBuffer');
      const sourceObject = assertObject(source, 'GPUCommandEncoder.copyTextureToBuffer', 'source');
      const destinationObject = assertObject(destination, 'GPUCommandEncoder.copyTextureToBuffer', 'destination');
      const sizeObject = assertObject(copySize, 'GPUCommandEncoder.copyTextureToBuffer', 'copySize');
      if (sourceObject.origin !== undefined) {
        assertObject(sourceObject.origin, 'GPUCommandEncoder.copyTextureToBuffer', 'source.origin');
      }
      assertIntegerInRange(destinationObject.offset ?? 0, 'GPUCommandEncoder.copyTextureToBuffer', 'destination.offset', { min: 0 });
      assertIntegerInRange(destinationObject.bytesPerRow ?? 0, 'GPUCommandEncoder.copyTextureToBuffer', 'destination.bytesPerRow', { min: 0 });
      assertIntegerInRange(destinationObject.rowsPerImage ?? 0, 'GPUCommandEncoder.copyTextureToBuffer', 'destination.rowsPerImage', { min: 0 });
      assertIntegerInRange(sizeObject.width, 'GPUCommandEncoder.copyTextureToBuffer', 'copySize.width', { min: 1, max: UINT32_MAX });
      assertIntegerInRange(sizeObject.height, 'GPUCommandEncoder.copyTextureToBuffer', 'copySize.height', { min: 1, max: UINT32_MAX });
      if (sizeObject.depthOrArrayLayers !== undefined) {
        assertIntegerInRange(sizeObject.depthOrArrayLayers, 'GPUCommandEncoder.copyTextureToBuffer', 'copySize.depthOrArrayLayers', { min: 1, max: UINT32_MAX });
      }
      backend.commandEncoderCopyTextureToBuffer(
        this,
        {
          texture: assertLiveResource(sourceObject.texture, 'GPUCommandEncoder.copyTextureToBuffer', 'GPUTexture'),
          mipLevel: sourceObject.mipLevel ?? 0,
          origin: {
            x: sourceObject.origin?.x ?? 0,
            y: sourceObject.origin?.y ?? 0,
            z: sourceObject.origin?.z ?? 0,
          },
          aspect: sourceObject.aspect,
        },
        {
          buffer: assertLiveResource(destinationObject.buffer, 'GPUCommandEncoder.copyTextureToBuffer', 'GPUBuffer'),
          offset: destinationObject.offset ?? 0,
          bytesPerRow: destinationObject.bytesPerRow ?? 0,
          rowsPerImage: destinationObject.rowsPerImage ?? 0,
        },
        {
          width: sizeObject.width,
          height: sizeObject.height,
          depthOrArrayLayers: sizeObject.depthOrArrayLayers ?? 1,
        },
      );
    }

    writeTimestamp(querySet, queryIndex) {
      this._assertOpen('GPUCommandEncoder.writeTimestamp');
      const querySetNative = assertLiveResource(querySet, 'GPUCommandEncoder.writeTimestamp', 'GPUQuerySet');
      assertIntegerInRange(queryIndex, 'GPUCommandEncoder.writeTimestamp', 'queryIndex', { min: 0, max: UINT32_MAX });
      if (queryIndex >= querySet.count) {
        failValidation('GPUCommandEncoder.writeTimestamp', `queryIndex ${queryIndex} exceeds querySet count ${querySet.count}`);
      }
      backend.commandEncoderWriteTimestamp(this, querySetNative, queryIndex);
    }

    resolveQuerySet(querySet, firstQuery, queryCount, destination, destinationOffset) {
      this._assertOpen('GPUCommandEncoder.resolveQuerySet');
      const querySetNative = assertLiveResource(querySet, 'GPUCommandEncoder.resolveQuerySet', 'GPUQuerySet');
      assertIntegerInRange(firstQuery, 'GPUCommandEncoder.resolveQuerySet', 'firstQuery', { min: 0, max: UINT32_MAX });
      assertIntegerInRange(queryCount, 'GPUCommandEncoder.resolveQuerySet', 'queryCount', { min: 1, max: UINT32_MAX });
      if (firstQuery + queryCount > querySet.count) {
        failValidation('GPUCommandEncoder.resolveQuerySet', `firstQuery ${firstQuery} + queryCount ${queryCount} exceeds querySet count ${querySet.count}`);
      }
      const destinationNative = assertLiveResource(destination, 'GPUCommandEncoder.resolveQuerySet', 'GPUBuffer');
      assertIntegerInRange(destinationOffset, 'GPUCommandEncoder.resolveQuerySet', 'destinationOffset', { min: 0 });
      backend.commandEncoderResolveQuerySet(this, querySetNative, firstQuery, queryCount, destinationNative, destinationOffset);
    }

    finish() {
      this._assertOpen('GPUCommandEncoder.finish');
      return backend.commandEncoderFinish(this);
    }
  }

  classes = {
    DoeGPUComputePassEncoder,
    DoeGPURenderPassEncoder,
    DoeGPUCommandEncoder,
  };
  return classes;
}

export {
  createEncoderClasses,
};
