const provider = await import(process.env.PROFILE_PROVIDER);
export const globals = provider.globals;
export function create(options) {
  const gpu = provider.create(process.env.PROFILE_PROVIDER.includes("node_modules/webgpu") ? [...options, "disable-dawn-features=timestamp_quantization"] : options);
  const requestAdapter = gpu.requestAdapter.bind(gpu);
  gpu.requestAdapter = async (...args) => {
    const adapter = await requestAdapter(...args);
    const requestDevice = adapter.requestDevice.bind(adapter);
    adapter.requestDevice = async (descriptor = {}) => {
      const device = await requestDevice({...descriptor, requiredFeatures: [...(descriptor.requiredFeatures ?? []), 'timestamp-query']});
      const U = globals.GPUBufferUsage;
      const query = device.createQuerySet({type:'timestamp',count:2048});
      const resolved = device.createBuffer({size:524288,usage:U.QUERY_RESOLVE|U.COPY_SRC});
      const readback = device.createBuffer({size:524288,usage:U.COPY_DST|U.MAP_READ});
      device.pushErrorScope("validation");
      let nextQuery=0, nextEpoch=0, collectedEpoch=0;
      const createEncoder=device.createCommandEncoder.bind(device);
      device.createCommandEncoder=(...args)=>{
        const encoder=createEncoder(...args);
        const begin=encoder.beginComputePass.bind(encoder);
        const finish=encoder.finish.bind(encoder);
        let firstQuery=nextQuery, passes=0;
        encoder.beginComputePass=(desc={})=>{const index=nextQuery;nextQuery+=2;passes++;return begin({...desc,timestampWrites:{querySet:query,beginningOfPassWriteIndex:index,endOfPassWriteIndex:index+1}});};
        encoder.finish=(...args)=>{if(passes){if(passes!==2)throw Error('unexpected UMAP passes');encoder.resolveQuerySet(query,firstQuery,passes*2,resolved,nextEpoch*256);encoder.copyBufferToBuffer(resolved,nextEpoch*256,readback,nextEpoch*256,passes*16);nextEpoch++;}return finish(...args);};
        return encoder;
      };
      const createBuffer=device.createBuffer.bind(device);
      device.createBuffer=(desc)=>{
        const buffer=createBuffer(desc);
        if(desc.usage & U.MAP_READ){const map=buffer.mapAsync.bind(buffer);buffer.mapAsync=async (...args)=>{await map(...args);await readback.mapAsync(globals.GPUMapMode.READ);const stamps=new BigUint64Array(readback.getMappedRange());const rows=[];for(let epoch=collectedEpoch;epoch<nextEpoch;epoch++){const i=epoch*32;rows.push({epoch,sgdNs:Number(stamps[i+1]-stamps[i]),applyNs:Number(stamps[i+3]-stamps[i+2])});}nextQuery=0;nextEpoch=0;collectedEpoch=0;readback.unmap();const error=await device.popErrorScope();if(error)throw Error(error.message);device.pushErrorScope("validation");console.log('DOE_GPU_PROFILE='+JSON.stringify({rows}));};}
        return buffer;
      };
      return device;
    };
    return adapter;
  };
  return gpu;
}
