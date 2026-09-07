"""Isolate the first changed attention output from retained full-model tensors."""
import hashlib
import json
import math
from pathlib import Path
import struct

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
SOURCE = HERE.parent / '20260907-linux-completion'
LAYER = 2
STEP = 1
HEAD_DIM = 256
HEADS = 4
KV_HEADS = 1
PREFILL = 12
KV_LEN = PREFILL + STEP
SCALE = 1 / math.sqrt(HEAD_DIM)

def sha(data):
    return hashlib.sha256(data).hexdigest()

def tensor(lane, step, stage, name):
    base = SOURCE / f'gemma270m-{lane}-node'
    metadata = json.loads((base / 'model_checkpoints.json').read_text())
    record = next(r for r in metadata['steps'][step]['checkpoints'][stage]['records']
                  if r['opId'] == f'layer.{LAYER}.attn.{name}')
    info = record['dataArtifact']
    with (base / info['path']).open('rb') as stream:
        stream.seek(info['byteOffset'])
        data = stream.read(info['byteLength'])
    assert sha(data) == info['sha256']
    return data

def floats(data):
    return struct.unpack('<' + 'f' * (len(data) // 4), data)

inputs = {
    'q.f32': tensor('W0', STEP, 'rope', 'q_rope'),
    'k.f32': tensor('W0', 0, 'rope', 'k_rope') + tensor('W0', STEP, 'rope', 'k_rope'),
    'v.f32': tensor('W0', 0, 'qkv', 'v_proj') + tensor('W0', STEP, 'qkv', 'v_proj'),
}
assert inputs['q.f32'] == tensor('D0', STEP, 'rope', 'q_rope')
assert inputs['k.f32'] == tensor('D0', 0, 'rope', 'k_rope') + tensor('D0', STEP, 'rope', 'k_rope')
assert inputs['v.f32'] == tensor('D0', 0, 'qkv', 'v_proj') + tensor('D0', STEP, 'qkv', 'v_proj')
for kind in ('k', 'v'):
    inputs[f'{kind}.f16'] = b''.join(struct.pack('<e', x) for x in floats(inputs[f'{kind}.f32']))
uniform = bytearray(64)
struct.pack_into('<5If2If6I', uniform, 0, HEADS, KV_HEADS, HEAD_DIM, KV_LEN, 1,
                 SCALE, 1, PREFILL, 0.0, 512, 0, 0, 256, 0, 0)
inputs['uniform.bin'] = uniform
for lane in ('W0', 'D0'):
    inputs[f'{lane}-model.f32'] = tensor(lane, STEP, 'attention', 'core_out')
q = floats(inputs['q.f32'])
k = struct.unpack('<' + 'e' * (len(inputs['k.f16']) // 2), inputs['k.f16'])
v = struct.unpack('<' + 'e' * (len(inputs['v.f16']) // 2), inputs['v.f16'])
reference = []
for head in range(HEADS):
    scores = [math.fsum(q[head * HEAD_DIM + d] * k[token * HEAD_DIM + d]
                       for d in range(HEAD_DIM)) * SCALE for token in range(KV_LEN)]
    probabilities = [math.exp(score - max(scores)) for score in scores]
    total = math.fsum(probabilities)
    reference.extend(math.fsum(probabilities[t] * v[t * HEAD_DIM + d]
                               for t in range(KV_LEN)) / total for d in range(HEAD_DIM))
inputs['cpu-f64.f64'] = struct.pack('<' + 'd' * len(reference), *reference)
shader = ROOT / 'bench/out/external-projects/doppler/upstream/src/gpu/kernels/attention_decode_online_head256_f16kv.wgsl'
inputs['attention.wgsl'] = shader.read_bytes()
for name, data in inputs.items():
    (HERE / name).write_bytes(data)
(HERE / 'inputs.sha256').write_text(''.join(f'{sha(data)}  {name}\n' for name, data in inputs.items()))
print('Retained Q/K/V inputs agree byte-for-byte before first changed attention output.')
for lane in ('W0', 'D0'):
    print(lane, 'model maximum absolute error against reconstructed f64 reference:',
          max(abs(a - b) for a, b in zip(floats(inputs[f'{lane}-model.f32']), reference)))
