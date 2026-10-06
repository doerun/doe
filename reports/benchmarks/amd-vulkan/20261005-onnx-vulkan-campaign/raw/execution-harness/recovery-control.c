#include "dawn/dawn_proc_table.h"
#include <stdint.h>
#include <string.h>

typedef const char* (*TakeError)(void);

/* Failure must leave the same instance/device usable. No submission is cancelled. */
int doeRecoverableControl(const DawnProcTable* table, WGPUInstance instance,
                         WGPUDevice device, TakeError take_error) {
    WGPUChainedStruct unsupported = {0};
    unsupported.sType = WGPUSType_DawnTogglesDescriptor;
    WGPUInstanceDescriptor invalid = {0};
    invalid.nextInChain = &unsupported;
    if (table->createInstance(&invalid) != NULL) return 1;
    const char* error = take_error();
    if (!error || strcmp(error, "UnsupportedDawnDescriptorChain: createInstance")) return 2;
    if (take_error() != NULL) return 3;
    WGPUShaderModuleDescriptor shader = {0};
    shader.nextInChain = &unsupported;
    if (table->deviceCreateShaderModule(device, &shader) != NULL) return 4;
    error = take_error();
    if (!error || strcmp(error, "UnsupportedDawnDescriptorChain: deviceCreateShaderModule")) return 5;
    WGPULimits limits = {0};
    WGPUChainedStruct unsupported_out = {0};
    unsupported_out.sType = WGPUSType_DawnTogglesDescriptor;
    limits.nextInChain = &unsupported_out;
    if (table->deviceGetLimits(device, &limits) != WGPUStatus_Error) return 6;
    error = take_error();
    if (!error || strcmp(error, "UnsupportedDawnDescriptorChain: deviceGetLimits")) return 7;
    limits.nextInChain = NULL;
    if (table->deviceGetLimits(device, &limits) != WGPUStatus_Success) return 8;
    WGPUShaderSourceWGSL source = {0};
    source.chain.sType = WGPUSType_ShaderSourceWGSL;
    source.code = (WGPUStringView){"@compute @workgroup_size(1) fn main() {}", WGPU_STRLEN};
    shader.nextInChain = &source.chain;
    WGPUShaderModule module = table->deviceCreateShaderModule(device, &shader);
    if (!module || take_error() != NULL) return 9;
    table->shaderModuleRelease(module);
    (void)instance;
    return 0;
}
