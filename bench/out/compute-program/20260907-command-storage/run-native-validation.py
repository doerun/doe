"""Execute public C regressions and reject Vulkan validation or synchronization errors."""
from pathlib import Path
import json
import os
import subprocess

root = Path(__file__).resolve().parent/'final-validation'
layer = Path.cwd()/'bench/out/compute-program/depth-qualification-tmp/vulkan-validation/extracted'
environment = dict(os.environ,
                   VK_LAYER_PATH=str(layer/'usr/share/vulkan/explicit_layer.d'),
                   VK_INSTANCE_LAYERS='VK_LAYER_KHRONOS_validation',VK_LAYER_VALIDATE_SYNC='1',
                   VK_LOADER_DEBUG='layer',LD_LIBRARY_PATH=str(layer/'usr/lib/x86_64-linux-gnu'))
commands=[]
for name in ['native_async_pipeline','native_recorded_compute']:
    command=[str(root/name)]
    commands.append(command)
    result=subprocess.run(command,env=environment,capture_output=True,text=True,timeout=120)
    (root/f'{name}.stdout').write_text(result.stdout)
    (root/f'{name}.stderr').write_text(result.stderr)
    assert result.returncode == 0, (name,result.returncode)
    assert 'VK_LAYER_KHRONOS_validation' in result.stderr
    assert 'Validation Error:' not in result.stderr and 'SYNC-HAZARD' not in result.stderr
    print(name,'PASS: active validation layer; no validation errors or synchronization hazards',flush=True)
(root/'native-c-run.command.json').write_text(json.dumps(commands,indent=2)+'\n')
