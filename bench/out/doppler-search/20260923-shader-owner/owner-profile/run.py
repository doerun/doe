from pathlib import Path
import hashlib,json,os,subprocess,sys
repo=Path('/home/x/deco/doe');sys.path.insert(0,str(repo))
from bench.lib.compute_program_gpu_activity import detect_target,read_snapshot,reject_activity,read_boot_id
root=repo/'bench/out/doppler-search/20260923-shader-owner/owner-profile'
policy=json.loads((root/'policy.json').read_text());target=detect_target()
for index,provider in enumerate(['doe','dawn']):
 output=root/f'{index}-{provider}';before=read_snapshot(target)
 env=dict(os.environ,DOE_WEBGPU_LIB=str(repo/'bench/out/doppler-search/20260923-shader-owner/owner-native/lib/libwebgpu_doe.so'),DOPPLER_TIMING_OUTPUT=str(output),DOPPLER_TIMING_PROVIDER=provider)
 print('START',index,provider,flush=True)
 with (root/f'{index}-{provider}.log').open('w') as log, (root/'probe.mjs').open() as script:
  p=subprocess.run(['timeout','180s','node','--input-type=module'],stdin=script,stdout=log,stderr=subprocess.STDOUT,env=env,cwd='/var/tmp/doppler-startup-reuse-20260920/consumer')
 after=read_snapshot(target);activity={'schemaVersion':2,'bootId':read_boot_id(),'target':target,'snapshots':[before,after]}
 try: reject_activity([before,after],target['pciDevice']);activity['admitted']=True
 except ValueError as e: activity['admitted']=False;activity['error']=str(e)
 (root/f'{index}-{provider}-activity.json').write_text(json.dumps(activity,indent=2))
 print('END',index,provider,'exit',p.returncode,'activity',activity['admitted'],flush=True)
 if p.returncode or not activity['admitted']:sys.exit(1)
