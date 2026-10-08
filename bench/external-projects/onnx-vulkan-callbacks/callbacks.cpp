// Bounded consumer callback contracts; emits observations, never timings.
#include "dawn/dawn_proc_table.h"
#include <dlfcn.h>
#include <atomic>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <thread>
#include <vector>
#include <filesystem>

static thread_local unsigned phase;
static const DawnProcTable* p;
static WGPUInstance instance;
static std::chrono::nanoseconds deadline;
static unsigned failures;
static std::vector<uint64_t> identities;
struct Capture {
    std::atomic<unsigned> count{0}, status{0}, deliveryPhase{0}, errorType{0};
    std::atomic<void*> object{nullptr};
    void record(unsigned s, void* o=nullptr, unsigned e=0) {
        status.store(s); object.store(o); errorType.store(e); deliveryPhase.store(phase);
        count.fetch_add(1, std::memory_order_release);
    }
};
static unsigned drmClients() {
    unsigned count=0;
    for(const auto& entry:std::filesystem::directory_iterator("/proc/self/fd")) {
        std::error_code error;
        auto target=std::filesystem::read_symlink(entry.path(),error).string();
        if(!error && target.rfind("/dev/dri/",0)==0) ++count;
    }
    return count;
}
static WGPUStringView text(const char* s) { return {s, std::strlen(s)}; }
static void check(const char* name, bool passed) {
    std::printf("{\"kind\":\"check\",\"name\":\"%s\",\"passed\":%s}\n",name,passed?"true":"false");
    if (!passed) ++failures;
}
static void adapterCB(WGPURequestAdapterStatus s,WGPUAdapter o,WGPUStringView,void* d,void*) { static_cast<Capture*>(d)->record(s,o); }
static void deviceCB(WGPURequestDeviceStatus s,WGPUDevice o,WGPUStringView,void* d,void*) { static_cast<Capture*>(d)->record(s,o); }
static void mapCB(WGPUMapAsyncStatus s,WGPUStringView,void* d,void*) { static_cast<Capture*>(d)->record(s); }
static void queueCB(WGPUQueueWorkDoneStatus s,WGPUStringView,void* d,void*) { static_cast<Capture*>(d)->record(s); }
static void pipelineCB(WGPUCreatePipelineAsyncStatus s,WGPUComputePipeline o,WGPUStringView,void* d,void*) { static_cast<Capture*>(d)->record(s,o); }
static void scopeCB(WGPUPopErrorScopeStatus s,WGPUErrorType e,WGPUStringView,void* d,void*) { static_cast<Capture*>(d)->record(s,nullptr,e); }
static void compilationCB(WGPUCompilationInfoRequestStatus s,const WGPUCompilationInfo*,void* d,void*) { static_cast<Capture*>(d)->record(s); }
static bool wait(WGPUFuture f) {
    WGPUFutureWaitInfo w{f,false};
    phase=2;
    auto status=p->instanceWaitAny(instance,1,&w,static_cast<uint64_t>(deadline.count()));
    phase=0;
    return status==WGPUWaitStatus_Success && w.completed;
}
static void observe(const char* name,WGPUCallbackMode mode,WGPUFuture future,Capture& c,unsigned expected=1) {
    phase=0;
    unsigned before=c.count.load(std::memory_order_acquire);
    unsigned afterEvents=before;
    if(mode==WGPUCallbackMode_WaitAnyOnly) {
        phase=3; p->instanceProcessEvents(instance); phase=0;
        afterEvents=c.count.load(std::memory_order_acquire);
    } else if(mode==WGPUCallbackMode_AllowProcessEvents) {
        auto until=std::chrono::steady_clock::now()+deadline;
        do { phase=3; p->instanceProcessEvents(instance); phase=0; std::this_thread::yield(); }
        while(c.count.load(std::memory_order_acquire)==0 && std::chrono::steady_clock::now()<until);
        afterEvents=c.count.load(std::memory_order_acquire);
    }
    bool waited=wait(future);
    unsigned count=c.count.load(std::memory_order_acquire);
    unsigned delivered=c.deliveryPhase.load();
    bool placement=mode==WGPUCallbackMode_AllowSpontaneous ||
        (mode==WGPUCallbackMode_WaitAnyOnly ? before==0 && afterEvents==0 && delivered==2 : before==0 && delivered==3);
    bool unique=true; for(auto old:identities) if(old==future.id) unique=false;
    identities.push_back(future.id);
    bool passed=waited && count==1 && c.status.load()==expected && placement && unique;
    // Repeated wait and pump may observe completion but must never redeliver.
    bool repeated=wait(future); phase=3; p->instanceProcessEvents(instance); phase=0;
    passed=passed && repeated && c.count.load(std::memory_order_acquire)==1;
    std::printf("{\"kind\":\"callback\",\"operation\":\"%s\",\"mode\":%u,\"before\":%u,\"afterEvents\":%u,\"count\":%u,\"status\":%u,\"expectedStatus\":%u,\"errorType\":%u,\"phase\":%u,\"future\":%llu,\"unique\":%s,\"waited\":%s,\"repeated\":%s,\"passed\":%s}\n",name,unsigned(mode),before,afterEvents,count,c.status.load(),expected,c.errorType.load(),delivered,(unsigned long long)future.id,unique?"true":"false",waited?"true":"false",repeated?"true":"false",passed?"true":"false");
    if(!passed) ++failures;
}
static WGPUAdapter setupAdapter() {
    Capture c; WGPURequestAdapterOptions options{};options.backendType=WGPUBackendType_Vulkan;
    WGPURequestAdapterCallbackInfo info{};info.mode=WGPUCallbackMode_AllowSpontaneous;info.callback=adapterCB;info.userdata1=&c;
    auto f=p->instanceRequestAdapter(instance,&options,info);if(!wait(f)||c.status!=1||!c.object)std::exit(93);
    return static_cast<WGPUAdapter>(c.object.load());
}
static WGPUDevice setupDevice(WGPUAdapter adapter) {
    Capture c; WGPUDeviceDescriptor desc{};
    WGPURequestDeviceCallbackInfo info{};info.mode=WGPUCallbackMode_AllowSpontaneous;info.callback=deviceCB;info.userdata1=&c;
    auto f=p->adapterRequestDevice(adapter,&desc,info);if(!wait(f)||c.status!=1||!c.object)std::exit(94);
    return static_cast<WGPUDevice>(c.object.load());
}
static WGPUBuffer buffer(WGPUDevice device,WGPUBufferUsage usage) {
    WGPUBufferDescriptor desc{};desc.size=64;desc.usage=usage;
    auto b=p->deviceCreateBuffer(device,&desc);if(!b)std::exit(95);return b;
}
static WGPUFuture map(WGPUBuffer b,WGPUCallbackMode mode,Capture& c,size_t offset=0) {
    WGPUBufferMapCallbackInfo info{};info.mode=mode;info.callback=mapCB;info.userdata1=&c;
    phase=1;return p->bufferMapAsync(b,WGPUMapMode_Read,offset,64-offset,info);
}
int main(int argc,char** argv) {
    if(argc!=5)return 90;
    deadline=std::chrono::nanoseconds(std::strtoull(argv[4],nullptr,10));
    auto bridge=dlopen(argv[1],RTLD_NOW|RTLD_LOCAL);if(!bridge)return 91;
    using Init=const DawnProcTable*(*)(const char*);
    auto init=reinterpret_cast<Init>(dlsym(bridge,!std::strcmp(argv[3],"doe")?"doeDawnBridgeInitialize":"doeDawnBridgeInitializeControl"));
    p=init?init(argv[2]):nullptr;if(!p)return 92;
    WGPUInstanceFeatureName feature=WGPUInstanceFeatureName_TimedWaitAny;
    WGPUInstanceDescriptor desc{};desc.requiredFeatureCount=1;desc.requiredFeatures=&feature;
    unsigned initialDrm=drmClients();
    instance=p->createInstance(&desc);if(!instance)return 93;
    auto adapter=setupAdapter();
    WGPUAdapterInfo hardware{};auto hardwareStatus=p->adapterGetInfo(adapter,&hardware);
    std::printf("{\"kind\":\"hardware\",\"vendorId\":%u,\"deviceId\":%u,\"backend\":%u}\n",hardware.vendorID,hardware.deviceID,unsigned(hardware.backendType));
    check("physical-amd-vulkan",hardwareStatus==WGPUStatus_Success && hardware.vendorID==0x1002 && hardware.backendType==WGPUBackendType_Vulkan);
    p->adapterInfoFreeMembers(hardware);
    auto device=setupDevice(adapter); auto queue=p->deviceGetQueue(device);
    const char* source="@compute @workgroup_size(1) fn main() {}";
    WGPUShaderSourceWGSL wgsl{};wgsl.chain.sType=WGPUSType_ShaderSourceWGSL;wgsl.code=text(source);
    WGPUShaderModuleDescriptor shaderDesc{};shaderDesc.nextInChain=&wgsl.chain;
    auto shader=p->deviceCreateShaderModule(device,&shaderDesc);if(!shader)return 96;
    for(auto mode:{WGPUCallbackMode_WaitAnyOnly,WGPUCallbackMode_AllowProcessEvents,WGPUCallbackMode_AllowSpontaneous}) {
        Capture a;WGPURequestAdapterOptions options{};options.backendType=WGPUBackendType_Vulkan;
        WGPURequestAdapterCallbackInfo ai{};ai.mode=mode;ai.callback=adapterCB;ai.userdata1=&a;
        phase=1;auto af=p->instanceRequestAdapter(instance,&options,ai);observe("RequestAdapter",mode,af,a);
        Capture d;WGPUDeviceDescriptor dd{};
        WGPURequestDeviceCallbackInfo di{};di.mode=mode;di.callback=deviceCB;di.userdata1=&d;
        phase=1;auto df=p->adapterRequestDevice(static_cast<WGPUAdapter>(a.object.load()),&dd,di);observe("RequestDevice",mode,df,d);
        if(auto o=d.object.load())p->deviceRelease(static_cast<WGPUDevice>(o));
        if(auto o=a.object.load())p->adapterRelease(static_cast<WGPUAdapter>(o));
        Capture pipeline;WGPUComputePipelineDescriptor pd{};pd.compute.module=shader;pd.compute.entryPoint=text("main");
        WGPUCreateComputePipelineAsyncCallbackInfo pi{};pi.mode=mode;pi.callback=pipelineCB;pi.userdata1=&pipeline;
        phase=1;auto pf=p->deviceCreateComputePipelineAsync(device,&pd,pi);observe("CreateComputePipelineAsync",mode,pf,pipeline);
        if(auto o=pipeline.object.load())p->computePipelineRelease(static_cast<WGPUComputePipeline>(o));
        Capture compilation;WGPUCompilationInfoCallbackInfo ci{};ci.mode=mode;ci.callback=compilationCB;ci.userdata1=&compilation;
        phase=1;auto cf=p->shaderModuleGetCompilationInfo(shader,ci);observe("ShaderModuleGetCompilationInfo",mode,cf,compilation);
        Capture scope;p->devicePushErrorScope(device,WGPUErrorFilter_Validation);
        WGPUPopErrorScopeCallbackInfo si{};si.mode=mode;si.callback=scopeCB;si.userdata1=&scope;
        phase=1;auto sf=p->devicePopErrorScope(device,si);observe("PopErrorScope",mode,sf,scope);
        check("empty-valid-scope-no-error",scope.errorType==WGPUErrorType_NoError);
        auto read=buffer(device,WGPUBufferUsage_MapRead|WGPUBufferUsage_CopyDst);
        auto write=buffer(device,WGPUBufferUsage_CopySrc|WGPUBufferUsage_CopyDst);
        uint32_t pattern[16];for(unsigned i=0;i<16;++i)pattern[i]=0x12340000+i;
        p->queueWriteBuffer(queue,write,0,pattern,sizeof(pattern));
        WGPUCommandEncoderDescriptor ed{};auto encoder=p->deviceCreateCommandEncoder(device,&ed);
        p->commandEncoderCopyBufferToBuffer(encoder,write,0,read,0,sizeof(pattern));
        WGPUCommandBufferDescriptor cbd{};auto command=p->commandEncoderFinish(encoder,&cbd);
        p->queueSubmit(queue,1,&command);p->commandBufferRelease(command);p->commandEncoderRelease(encoder);p->bufferRelease(write);
        Capture done;WGPUQueueWorkDoneCallbackInfo qi{};qi.mode=mode;qi.callback=queueCB;qi.userdata1=&done;
        phase=1;auto qf=p->queueOnSubmittedWorkDone(queue,qi);observe("QueueOnSubmittedWorkDone",mode,qf,done);
        Capture mapped;auto mf=map(read,mode,mapped);observe("BufferMapAsync",mode,mf,mapped);
        auto contents=p->bufferGetConstMappedRange(read,0,sizeof(pattern));
        std::printf("{\"kind\":\"readback\",\"available\":%s,\"values\":[",contents?"true":"false");
        for(unsigned i=0;i<16;++i) std::printf("%s%u",i?",":"",contents?static_cast<const uint32_t*>(contents)[i]:0);
        std::printf("]}\n");
        check("submitted-copy-readback",contents && !std::memcmp(contents,pattern,sizeof(pattern)));
        p->bufferUnmap(read);p->bufferRelease(read);
    }
    // Error recovery, mapping state, and cancellation before deferred delivery.
    auto read=buffer(device,WGPUBufferUsage_MapRead|WGPUBufferUsage_CopyDst);
    Capture invalid;p->devicePushErrorScope(device,WGPUErrorFilter_Validation);
    auto invalidFuture=map(read,WGPUCallbackMode_WaitAnyOnly,invalid,4);observe("invalid-map-alignment",WGPUCallbackMode_WaitAnyOnly,invalidFuture,invalid,WGPUMapAsyncStatus_Error);
    Capture captured;WGPUPopErrorScopeCallbackInfo si{};si.mode=WGPUCallbackMode_WaitAnyOnly;si.callback=scopeCB;si.userdata1=&captured;
    phase=1;auto scoped=p->devicePopErrorScope(device,si);observe("map-validation-error-scope",WGPUCallbackMode_WaitAnyOnly,scoped,captured);
    check("map-error-captured",captured.errorType==WGPUErrorType_Validation);
    Capture pending;auto pendingFuture=map(read,WGPUCallbackMode_WaitAnyOnly,pending);phase=0;
    auto mapState=p->bufferGetMapState(read);bool rangeUnavailable=p->bufferGetConstMappedRange(read,0,64)==nullptr;
    std::printf("{\"kind\":\"map-state\",\"state\":%u,\"rangeUnavailable\":%s}\n",unsigned(mapState),rangeUnavailable?"true":"false");
    check("map-state-pending",mapState==WGPUBufferMapState_Pending && rangeUnavailable);
    p->bufferUnmap(read);observe("unmap-pending",WGPUCallbackMode_WaitAnyOnly,pendingFuture,pending,WGPUMapAsyncStatus_Aborted);
    Capture reuse;auto reuseFuture=map(read,WGPUCallbackMode_WaitAnyOnly,reuse);observe("mapping-reuse",WGPUCallbackMode_WaitAnyOnly,reuseFuture,reuse);p->bufferUnmap(read);
    Capture destroyed;auto destroyedFuture=map(read,WGPUCallbackMode_WaitAnyOnly,destroyed);phase=0;p->bufferDestroy(read);p->bufferRelease(read);
    observe("destroy-pending-caller-release",WGPUCallbackMode_WaitAnyOnly,destroyedFuture,destroyed,WGPUMapAsyncStatus_Aborted);
    // A pop without a scope returns an explicit error and is recoverable.
    Capture empty;si.userdata1=&empty;phase=1;auto ef=p->devicePopErrorScope(device,si);observe("pop-without-scope",WGPUCallbackMode_WaitAnyOnly,ef,empty,WGPUPopErrorScopeStatus_Error);
    check("failed-pop-no-error-type",empty.errorType==WGPUErrorType_NoError);
    // Separate instance pumps cannot deliver this instance's events.
    Capture isolated;WGPUQueueWorkDoneCallbackInfo qi{};qi.mode=WGPUCallbackMode_AllowProcessEvents;qi.callback=queueCB;qi.userdata1=&isolated;
    phase=1;auto iso=p->queueOnSubmittedWorkDone(queue,qi);phase=0;
    auto second=p->createInstance(&desc);p->instanceProcessEvents(second);p->instanceRelease(second);
    check("instance-pump-isolation",isolated.count==0);observe("isolated-queue",WGPUCallbackMode_AllowProcessEvents,iso,isolated);
    // Matching WaitAny selects its supplied future and leaves another callback pending.
    Capture selected, unselected;qi.mode=WGPUCallbackMode_WaitAnyOnly;qi.userdata1=&selected;
    phase=1;auto selectedFuture=p->queueOnSubmittedWorkDone(queue,qi);qi.userdata1=&unselected;
    auto unselectedFuture=p->queueOnSubmittedWorkDone(queue,qi);phase=0;
    check("wait-selects-supplied-future",wait(selectedFuture) && selected.count==1 && unselected.count==0 && selectedFuture.id!=unselectedFuture.id);
    bool selectedAgain=wait(selectedFuture);
    std::printf("{\"kind\":\"selection\",\"count\":%u,\"phase\":%u,\"otherCount\":%u,\"selectedAgain\":%s}\n",selected.count.load(),selected.deliveryPhase.load(),unselected.count.load(),selectedAgain?"true":"false");
    check("selected-queue-exactly-once",selected.count==1 && selectedAgain);
    observe("unselected-queue",WGPUCallbackMode_WaitAnyOnly,unselectedFuture,unselected);
    // ProcessEvents-capable callbacks can also be completed inside matching WaitAny.
    Capture pumpedByWait;qi.mode=WGPUCallbackMode_AllowProcessEvents;qi.userdata1=&pumpedByWait;
    phase=1;auto wf=p->queueOnSubmittedWorkDone(queue,qi);phase=0;
    check("process-events-mode-wait-any",pumpedByWait.count==0 && wait(wf) && pumpedByWait.count==1 && pumpedByWait.deliveryPhase==2);
    // Descriptor snapshot errors obey the mode and permit a later valid request.
    Capture invalidPipeline;WGPUComputePipelineDescriptor invalidDesc{};WGPUConstantEntry invalidConstant{};invalidConstant.nextInChain=&wgsl.chain;invalidConstant.key=text("missing");invalidConstant.value=1;
    invalidDesc.compute.constantCount=1;invalidDesc.compute.constants=&invalidConstant;
    invalidDesc.compute.module=shader;invalidDesc.compute.entryPoint=text("main");
    WGPUCreateComputePipelineAsyncCallbackInfo invalidInfo{};invalidInfo.mode=WGPUCallbackMode_WaitAnyOnly;invalidInfo.callback=pipelineCB;invalidInfo.userdata1=&invalidPipeline;
    phase=1;auto invalidPipelineFuture=p->deviceCreateComputePipelineAsync(device,&invalidDesc,invalidInfo);
    observe("pipeline-unsupported-descriptor",WGPUCallbackMode_WaitAnyOnly,invalidPipelineFuture,invalidPipeline,WGPUCreatePipelineAsyncStatus_ValidationError);
    if(auto o=invalidPipeline.object.load())p->computePipelineRelease(static_cast<WGPUComputePipeline>(o));
    Capture validPipeline;invalidDesc.compute.constantCount=0;invalidDesc.compute.constants=nullptr;invalidInfo.userdata1=&validPipeline;
    phase=1;auto validPipelineFuture=p->deviceCreateComputePipelineAsync(device,&invalidDesc,invalidInfo);
    observe("pipeline-reuse-after-error",WGPUCallbackMode_WaitAnyOnly,validPipelineFuture,validPipeline);
    if(auto o=validPipeline.object.load())p->computePipelineRelease(static_cast<WGPUComputePipeline>(o));
    // Caller handles may be dropped while the live instance drains obligations.
    Capture released;qi.mode=WGPUCallbackMode_WaitAnyOnly;qi.userdata1=&released;
    phase=1;auto rf=p->queueOnSubmittedWorkDone(queue,qi);phase=0;
    p->shaderModuleRelease(shader);p->queueRelease(queue);p->deviceRelease(device);p->adapterRelease(adapter);
    observe("pending-queue-caller-release",WGPUCallbackMode_WaitAnyOnly,rf,released);
    p->instanceRelease(instance);
    unsigned finalDrm=drmClients();
    std::printf("{\"kind\":\"drm\",\"initial\":%u,\"final\":%u}\n",initialDrm,finalDrm);
    check("native-drm-release-before-process-exit",initialDrm==finalDrm);
    std::printf("{\"kind\":\"summary\",\"failures\":%u,\"passed\":%s}\n",failures,failures==0?"true":"false");
    return failures==0?0:1;
}
