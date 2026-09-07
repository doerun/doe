"""Observe attention intermediates without replacing its output calculation."""
from pathlib import Path
import subprocess
import struct

here = Path(__file__).resolve().parent
source = (here / 'attention.wgsl').read_text()
stages = [
    ('score', '        let chunk_max = subgroupMax(score);', 'score'),
    ('exp', '        let chunk_sum = subgroupAdd(exp_score);', 'exp_score'),
    ('sum', '        running_sum = running_sum * rescale + global_sum;', 'global_sum'),
    ('accum', '    output[q_offset + tid] = out_accum * inv_sum;', 'out_accum'),
]
for stage, anchor, value in stages:
    assert source.count(anchor) == 1
    shader = source.replace('var<workgroup> shared_q:',
        '@group(0) @binding(7) var<storage, read_write> debug_output: array<f32>;\n\nvar<workgroup> shared_q:')
    shader = shader.replace(anchor, f'        debug_output[q_offset + tid] = {value};\n' + anchor)
    path = here / f'{stage}.wgsl'
    path.write_text(shader)
    for lane in ('W0', 'D0'):
        output = here / f'{lane}-{stage}.f32'
        with (here / f'{lane}-{stage}.log').open('w') as log:
            subprocess.run(['node', str(here / 'run.mjs'), lane, str(path), str(output)],
                           stdout=log, stderr=subprocess.STDOUT, timeout=120, check=True)
        assert output.read_bytes() == (here / f'{lane}-model.f32').read_bytes(), (stage, lane, 'instrumentation changed final output')
    a = struct.unpack('<1024f', (here / f'W0-{stage}.f32.debug').read_bytes())
    b = struct.unpack('<1024f', (here / f'D0-{stage}.f32.debug').read_bytes())
    different = [i for i, (x, y) in enumerate(zip(a, b)) if x != y]
    print(stage, 'changed', len(different), 'first', different[:8],
          'maxAbs', max(abs(x-y) for x, y in zip(a,b)), flush=True)

anchor = '                    dot_accum = dot_accum + dot(shared_q[d4], k0) + dot(shared_q[d4 + 1u], k1);'
assert source.count(anchor) == 1
shader = source.replace('var<workgroup> shared_q:',
    '@group(0) @binding(7) var<storage, read_write> debug_output: array<f32>;\n\nvar<workgroup> shared_q:')
shader = shader.replace(anchor, anchor + '\n                    if (head_idx == 3u) { debug_output[tid * 32u + d4 / 2u] = dot_accum; }')
path = here / 'dot-accum.wgsl'
path.write_text(shader)
for lane in ('W0', 'D0'):
    output = here / f'{lane}-dot-accum.f32'
    with (here / f'{lane}-dot-accum.log').open('w') as log:
        subprocess.run(['node', str(here / 'run.mjs'), lane, str(path), str(output)],
                       stdout=log, stderr=subprocess.STDOUT, timeout=120, check=True)
    assert output.read_bytes() == (here / f'{lane}-model.f32').read_bytes(), ('dot-accum', lane)
a = struct.unpack('<1024f', (here / 'W0-dot-accum.f32.debug').read_bytes())
b = struct.unpack('<1024f', (here / 'D0-dot-accum.f32.debug').read_bytes())
for key in range(13):
    different = [i for i in range(32) if a[key*32+i] != b[key*32+i]]
    if different:
        print('key', key, 'first differing dot iteration', different[0],
              'Dawn', a[key*32+different[0]], 'Doe', b[key*32+different[0]], flush=True)
