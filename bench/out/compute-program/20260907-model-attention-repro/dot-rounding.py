"""Compare explicit four-component reduction orders with captured partials."""
from pathlib import Path
import ctypes
import itertools
import struct

p = Path(__file__).resolve().parent
fmaf = ctypes.CDLL('libm.so.6').fmaf
fmaf.argtypes = [ctypes.c_float] * 3
fmaf.restype = ctypes.c_float
def f32(x):
    return struct.unpack('<f', struct.pack('<f', x))[0]
q = struct.unpack('<1024f', (p / 'q.f32').read_bytes())[768:]
k = struct.unpack('<3328e', (p / 'k.f16').read_bytes())
actual = struct.unpack('<1024f', (p / 'W0-dot-accum.f32.debug').read_bytes())
ranked = []
for order in itertools.permutations(range(4)):
    for fused in itertools.product((False, True), repeat=3):
        mismatches = 0
        for key in range(13):
            accum = 0.0
            for block in range(32):
                for vec in range(2):
                    base = block * 8 + vec * 4
                    first = base + order[0]
                    dot = f32(q[first] * k[key*256+first])
                    for index, fusion in zip(order[1:], fused):
                        d = base + index
                        dot = fmaf(q[d], k[key*256+d], dot) if fusion else f32(f32(q[d]*k[key*256+d])+dot)
                    accum = f32(accum + dot)
                mismatches += accum != actual[key*32+block]
        ranked.append((mismatches, order, fused))
print(*sorted(ranked)[:12], sep='\n')
