// Independent public ABI lifecycle oracle; emits correctness observations only.
#include "dawn/dawn_proc_table.h"
#include <dlfcn.h>
#include <atomic>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <filesystem>

static const DawnProcTable* p;
static WGPUInstance instance;
static unsigned failures;
static unsigned phase;
static uint64_t deadline;
struct Capture {
    unsigned count=0, reason=0, delivery=0;
    WGPUDevice device=nullptr;
    bool pointer=false, message=false, release=false;
};
static void lost(const WGPUDevice* device,WGPUDeviceLostReason reason,WGPUStringView message,void* data,void* data2) {
    auto& c=*static_cast<Capture*>(data);
    c.pointer=device!=nullptr; c.device=device?*device:nullptr;
    c.reason=reason; c.message=message.data && message.length; c.delivery=phase; ++c.count;
    if(data2!=data) ++failures;
    if(c.release && c.device) p->deviceRelease(c.device);
}
static void check(const char* name,bool passed) {
    std::printf("{\"kind\":\"check\",\"name\":\"%s\",\"passed\":%s}\n",name,passed?"true":"false");
    if(!passed) ++failures;
}
static unsigned drm() {
    unsigned count=0;
    for(auto& entry:std::filesystem::directory_iterator("/proc/self/fd")) {
        std::error_code error; auto target=std::filesystem::read_symlink(entry.path(),error).string();
        if(!error && target.rfind("/dev/dri/",0)==0) ++count;
    }
    return count;
}
static bool wait(WGPUFuture future,uint64_t timeout=0) {
    WGPUFutureWaitInfo info{future,false}; phase=2;
    auto status=p->instanceWaitAny(instance,1,&info,timeout); phase=0;
    return status==WGPUWaitStatus_Success && info.completed;
}
static WGPUAdapter adapter() {
    WGPUAdapter result=nullptr;
    WGPURequestAdapterOptions options{}; options.backendType=WGPUBackendType_Vulkan;
    WGPURequestAdapterCallbackInfo info{}; info.mode=WGPUCallbackMode_AllowSpontaneous; info.userdata1=&result;
    info.callback=[](WGPURequestAdapterStatus s,WGPUAdapter a,WGPUStringView,void* d,void*) { if(s==WGPURequestAdapterStatus_Success) *static_cast<WGPUAdapter*>(d)=a; };
    auto f=p->instanceRequestAdapter(instance,&options,info); if(!wait(f,deadline)||!result) std::exit(93);
    return result;
}
static WGPUDevice device(WGPUAdapter adapter,WGPUCallbackMode mode,Capture& c,bool fail=false) {
    WGPUDevice result=nullptr; unsigned status=0;
    struct Reply { WGPUDevice* device; unsigned* status; } reply{&result,&status};
    WGPUDeviceDescriptor desc{};
    desc.deviceLostCallbackInfo.mode=mode; desc.deviceLostCallbackInfo.callback=lost;
    desc.deviceLostCallbackInfo.userdata1=&c; desc.deviceLostCallbackInfo.userdata2=&c;
    WGPUFeatureName feature=WGPUFeatureName_ChromiumExperimentalSubgroupMatrix;
    if(fail) { desc.requiredFeatureCount=1; desc.requiredFeatures=&feature; }
    WGPURequestDeviceCallbackInfo info{}; info.mode=WGPUCallbackMode_AllowSpontaneous; info.userdata1=&reply;
    info.callback=[](WGPURequestDeviceStatus s,WGPUDevice a,WGPUStringView,void* d,void*) { auto r=static_cast<Reply*>(d); *r->device=a; *r->status=s; };
    auto f=p->adapterRequestDevice(adapter,&desc,info);
    check(fail?"failed-request":"successful-request",wait(f,deadline) && status==(fail?WGPURequestDeviceStatus_Error:WGPURequestDeviceStatus_Success) && (fail?!result:bool(result)));
    return result;
}
static void observe(const char* name,WGPUCallbackMode mode,WGPUFuture f,Capture& c,unsigned reason,bool nullDevice,unsigned before) {
    unsigned after=before;
    phase=3; p->instanceProcessEvents(instance); phase=0; after=c.count;
    bool waited=f.id?wait(f):true;
    bool placement=mode==WGPUCallbackMode_AllowSpontaneous || (mode==WGPUCallbackMode_WaitAnyOnly?before==0 && after==0 && c.delivery==2:before==0 && c.delivery==3);
    bool pass=waited && c.count==1 && c.reason==reason && c.pointer && (nullDevice?!c.device:bool(c.device)) && placement;
    if(f.id) pass=wait(f)&&pass;
    p->instanceProcessEvents(instance); pass=pass&&c.count==1;
    std::printf("{\"kind\":\"loss\",\"operation\":\"%s\",\"mode\":%u,\"future\":%llu,\"before\":%u,\"afterEvents\":%u,\"count\":%u,\"reason\":%u,\"pointer\":%s,\"nullDevice\":%s,\"phase\":%u,\"waited\":%s,\"passed\":%s}\n",name,unsigned(mode),(unsigned long long)f.id,before,after,c.count,c.reason,c.pointer?"true":"false",c.device?"false":"true",c.delivery,waited?"true":"false",pass?"true":"false");
    if(!pass) ++failures;
}
static void submittedLifecycle(WGPUAdapter a) {
    Capture c;auto d=device(a,WGPUCallbackMode_WaitAnyOnly,c);auto queue=p->deviceGetQueue(d);
    WGPUBufferDescriptor bd{};bd.size=64;bd.usage=WGPUBufferUsage_CopySrc|WGPUBufferUsage_CopyDst;
    auto source=p->deviceCreateBuffer(d,&bd);bd.usage=WGPUBufferUsage_MapRead|WGPUBufferUsage_CopyDst;
    auto destination=p->deviceCreateBuffer(d,&bd);
    uint32_t expected[16];for(unsigned i=0;i<16;++i)expected[i]=0x65430000+i;
    p->queueWriteBuffer(queue,source,0,expected,sizeof(expected));
    auto copy=[&]() {
        WGPUCommandEncoderDescriptor ed{};auto encoder=p->deviceCreateCommandEncoder(d,&ed);
        p->commandEncoderCopyBufferToBuffer(encoder,source,0,destination,0,sizeof(expected));
        WGPUCommandBufferDescriptor cd{};auto command=p->commandEncoderFinish(encoder,&cd);
        p->queueSubmit(queue,1,&command);p->commandBufferRelease(command);p->commandEncoderRelease(encoder);
    };
    copy();unsigned mapStatus=0;
    WGPUBufferMapCallbackInfo map{};map.mode=WGPUCallbackMode_WaitAnyOnly;map.userdata1=&mapStatus;
    map.callback=[](WGPUMapAsyncStatus status,WGPUStringView,void* data,void*){*static_cast<unsigned*>(data)=status;};
    auto mapped=p->bufferMapAsync(destination,WGPUMapMode_Read,0,sizeof(expected),map);
    bool mappedOk=wait(mapped,deadline) && mapStatus==WGPUMapAsyncStatus_Success;
    auto bytes=mappedOk?p->bufferGetConstMappedRange(destination,0,sizeof(expected)):nullptr;
    std::printf("{\"kind\":\"readback\",\"values\":[");
    for(unsigned i=0;i<16;++i)std::printf("%s%u",i?",":"",bytes?static_cast<const uint32_t*>(bytes)[i]:0);
    std::printf("]}\n");
    check("unchanged-submitted-copy-oracle",bytes && !std::memcmp(bytes,expected,sizeof(expected)));
    p->bufferUnmap(destination);
    copy();unsigned doneStatus=0;
    WGPUQueueWorkDoneCallbackInfo done{};done.mode=WGPUCallbackMode_WaitAnyOnly;done.userdata1=&doneStatus;
    done.callback=[](WGPUQueueWorkDoneStatus status,WGPUStringView,void* data,void*){*static_cast<unsigned*>(data)=status;};
    auto completion=p->queueOnSubmittedWorkDone(queue,done);auto loss=p->deviceGetLostFuture(d);
    p->bufferRelease(source);phase=1;p->deviceDestroy(d);unsigned before=c.count;phase=0;
    observe("DestroyAfterSubmission",WGPUCallbackMode_WaitAnyOnly,loss,c,WGPUDeviceLostReason_Destroyed,false,before);
    check("submitted-completion-settles",wait(completion,deadline) && doneStatus==WGPUQueueWorkDoneStatus_Success);
    mapStatus=0;mapped=p->bufferMapAsync(destination,WGPUMapMode_Read,0,sizeof(expected),map);
    bool mapWaited=wait(mapped,deadline);
    std::printf("{\"kind\":\"post-loss-map\",\"status\":%u,\"waited\":%s}\n",mapStatus,mapWaited?"true":"false");
    check("post-loss-map-rejected",mapWaited && mapStatus==WGPUMapAsyncStatus_Aborted);
    p->bufferRelease(destination);p->queueRelease(queue);p->deviceRelease(d);
}
static void pipelineLoss(WGPUAdapter a) {
    Capture c;auto d=device(a,WGPUCallbackMode_WaitAnyOnly,c);
    const char* code="@compute @workgroup_size(1) fn main() {}";
    WGPUShaderSourceWGSL wgsl{};wgsl.chain.sType=WGPUSType_ShaderSourceWGSL;wgsl.code={code,std::strlen(code)};
    WGPUShaderModuleDescriptor sd{};sd.nextInChain=&wgsl.chain;auto shader=p->deviceCreateShaderModule(d,&sd);
    WGPUComputePipelineDescriptor descriptor{};descriptor.compute.module=shader;descriptor.compute.entryPoint={"main",4};
    struct PipelineCapture { unsigned count=0,status=0;WGPUComputePipeline pipeline=nullptr; } capture;
    WGPUCreateComputePipelineAsyncCallbackInfo info{};info.mode=WGPUCallbackMode_WaitAnyOnly;info.userdata1=&capture;
    info.callback=[](WGPUCreatePipelineAsyncStatus status,WGPUComputePipeline pipeline,WGPUStringView,void* data,void*) {
        auto& result=*static_cast<PipelineCapture*>(data);++result.count;result.status=status;result.pipeline=pipeline;
    };
    auto future=p->deviceCreateComputePipelineAsync(d,&descriptor,info);
    auto loss=p->deviceGetLostFuture(d);p->deviceDestroy(d);
    for(auto name:{"PendingPipelineAtDestroy","PipelineAfterDestroy"}) {
        bool waited=wait(future,deadline);
        bool pass=waited && capture.count==1 && capture.status==WGPUCreatePipelineAsyncStatus_Success && capture.pipeline;
        std::printf("{\"kind\":\"lost-pipeline\",\"operation\":\"%s\",\"count\":%u,\"status\":%u,\"pipeline\":%s,\"waited\":%s,\"passed\":%s}\n",name,capture.count,capture.status,capture.pipeline?"true":"false",waited?"true":"false",pass?"true":"false");
        if(!pass)++failures;
        if(capture.pipeline)p->computePipelineRelease(capture.pipeline);
        capture={};
        if(!std::strcmp(name,"PendingPipelineAtDestroy"))future=p->deviceCreateComputePipelineAsync(d,&descriptor,info);
    }
    observe("DestroyWithPendingPipeline",WGPUCallbackMode_WaitAnyOnly,loss,c,WGPUDeviceLostReason_Destroyed,false,0);
    p->shaderModuleRelease(shader);p->deviceRelease(d);
}
int main(int argc,char** argv) {
    if(argc!=5)return 90;
    std::setvbuf(stdout,nullptr,_IONBF,0);
    deadline=std::strtoull(argv[4],nullptr,10);
    auto bridge=dlopen(argv[1],RTLD_NOW|RTLD_LOCAL);if(!bridge)return 91;
    using Init=const DawnProcTable*(*)(const char*);
    auto init=reinterpret_cast<Init>(dlsym(bridge,!std::strcmp(argv[3],"dawn")?"doeDawnBridgeInitializeControl":"doeDawnBridgeInitialize"));
    p=init?init(argv[2]):nullptr;if(!p)return 92;
    unsigned initial=drm(); WGPUInstanceFeatureName features[]={WGPUInstanceFeatureName_TimedWaitAny,WGPUInstanceFeatureName_MultipleDevicesPerAdapter};
    WGPUInstanceDescriptor desc{}; desc.requiredFeatureCount=2;desc.requiredFeatures=features;instance=p->createInstance(&desc);
    auto a=adapter(); WGPUAdapterInfo hw{}; auto status=p->adapterGetInfo(a,&hw);
    std::printf("{\"kind\":\"hardware\",\"vendorId\":%u,\"deviceId\":%u,\"backend\":%u}\n",hw.vendorID,hw.deviceID,unsigned(hw.backendType));
    check("physical-amd-vulkan",status==WGPUStatus_Success && hw.vendorID==0x1002 && hw.backendType==WGPUBackendType_Vulkan);p->adapterInfoFreeMembers(hw);
    for(auto mode:{WGPUCallbackMode_WaitAnyOnly,WGPUCallbackMode_AllowProcessEvents,WGPUCallbackMode_AllowSpontaneous}) {
        Capture c; auto d=device(a,mode,c); auto f=p->deviceGetLostFuture(d);
        check("stable-loss-future",f.id && p->deviceGetLostFuture(d).id==f.id);
        WGPUFutureWaitInfo poll{f,false};
        check("pending-loss-poll",p->instanceWaitAny(instance,1,&poll,0)==WGPUWaitStatus_TimedOut && !poll.completed && c.count==0);
        phase=1; p->deviceDestroy(d); unsigned before=c.count; phase=0;
        observe("Destroy",mode,f,c,WGPUDeviceLostReason_Destroyed,false,before);
        p->deviceDestroy(d);p->deviceRelease(d);p->instanceProcessEvents(instance);
        check("destroy-release-exactly-once",c.count==1);

        Capture released; d=device(a,mode,released); f=p->deviceGetLostFuture(d);
        auto queue=p->deviceGetQueue(d); WGPUBufferDescriptor bd{}; bd.size=64;bd.usage=WGPUBufferUsage_CopyDst|WGPUBufferUsage_MapRead;
        auto b=p->deviceCreateBuffer(d,&bd);
        p->deviceAddRef(d); p->deviceRelease(d);check("remaining-external-reference",released.count==0);
        phase=1;p->deviceRelease(d);before=released.count;phase=0;
        observe("FinalReleaseWithResources",mode,f,released,WGPUDeviceLostReason_Destroyed,true,before);
        p->bufferRelease(b);p->queueRelease(queue);
        check("retained-resources-release-once",released.count==1);

        // Failed creation is pumpable through ProcessEvents; no device exposes its lost future.
        if(mode!=WGPUCallbackMode_WaitAnyOnly) {
            Capture failed; device(a,mode,failed,true); before=failed.count;
            observe("FailedCreation",mode,{0},failed,WGPUDeviceLostReason_FailedCreation,true,before);
            Capture recovered;d=device(a,mode,recovered);f=p->deviceGetLostFuture(d);phase=1;p->deviceDestroy(d);before=recovered.count;phase=0;
            observe("ReuseAfterFailedCreation",mode,f,recovered,WGPUDeviceLostReason_Destroyed,false,before);p->deviceRelease(d);
        }
    }
    submittedLifecycle(a);
    pipelineLoss(a);
    Capture reentrant;reentrant.release=true;auto d=device(a,WGPUCallbackMode_WaitAnyOnly,reentrant);auto f=p->deviceGetLostFuture(d);
    phase=1;p->deviceDestroy(d);unsigned before=reentrant.count;phase=0;
    observe("ReleaseInsideLostCallback",WGPUCallbackMode_WaitAnyOnly,f,reentrant,WGPUDeviceLostReason_Destroyed,false,before);
    // A deferred explicit loss must pass null if the last external ref goes first.
    Capture deferred;d=device(a,WGPUCallbackMode_WaitAnyOnly,deferred);f=p->deviceGetLostFuture(d);p->deviceDestroy(d);p->deviceRelease(d);
    observe("ReleaseBeforeLostDelivery",WGPUCallbackMode_WaitAnyOnly,f,deferred,WGPUDeviceLostReason_Destroyed,true,0);
    p->adapterRelease(a);p->instanceProcessEvents(instance);p->instanceRelease(instance);
    unsigned final=drm();check("drm-client-baseline-restored",initial==final);
    std::printf("{\"kind\":\"summary\",\"failures\":%u,\"initialDrmClients\":%u,\"finalDrmClients\":%u}\n",failures,initial,final);
    return failures?1:0;
}
