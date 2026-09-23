from pathlib import Path
import hashlib,json,os,subprocess,sys
repo=Path('/home/x/deco/doe');sys.path.insert(0,str(repo))
from bench.lib.compute_program_gpu_activity import detect_target,read_snapshot,reject_activity,read_boot_id
root=repo/'bench/out/doppler-search/20260923-shader-owner/owner-compare'
for key in ('LD_PRELOAD', 'RADV_DEBUG', 'DOE_VULKAN_REQUIRED_SUBGROUP_SIZE'):
 if os.environ.get(key): raise RuntimeError(f'Diagnostic environment forbidden: {key}')
policy=json.loads((root/'policy.json').read_text());target=detect_target()
for index,variant in enumerate(policy['order']):
 provider='dawn' if variant=='dawn' else 'doe'
 library=repo/('bench/out/doppler-search/20260923-shader-owner/owner-native/lib/libwebgpu_doe.so' if variant=='candidate' else 'bench/out/doppler-search/20260920-independent-loops/native/lib/libwebgpu_doe.so')
 output=root/f'{index}-{variant}';before=read_snapshot(target)
 env=dict(os.environ,DOE_WEBGPU_LIB=str(library),DOPPLER_TIMING_VARIANT=variant,DOPPLER_TIMING_OUTPUT=str(output),DOPPLER_TIMING_PROVIDER=provider)
 print('START',index,variant,flush=True)
 with (root/f'{index}-{variant}.log').open('w') as log, (root/'probe.mjs').open() as script:
  p=subprocess.run(['timeout','180s','node','--input-type=module'],stdin=script,stdout=log,stderr=subprocess.STDOUT,env=env,cwd='/var/tmp/doppler-startup-reuse-20260920/consumer')
 after=read_snapshot(target);activity={'schemaVersion':2,'bootId':read_boot_id(),'target':target,'snapshots':[before,after]}
 try: reject_activity([before,after],target['pciDevice']);activity['admitted']=True
 except ValueError as e: activity['admitted']=False;activity['error']=str(e)
 (root/f'{index}-{variant}-activity.json').write_text(json.dumps(activity,indent=2))
 print('END',index,variant,'exit',p.returncode,'activity',activity['admitted'],flush=True)
 if p.returncode or not activity['admitted']:sys.exit(1)
