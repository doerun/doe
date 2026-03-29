struct Uniforms {
  seq_len: u32,
  head_dim: u32,
  scale: f32,
  _pad0: f32,
};

@group(0) @binding(0) var<uniform> params: Uniforms;
@group(0) @binding(1) var<storage, read> q: array<f32>;
@group(0) @binding(2) var<storage, read> k: array<f32>;
@group(0) @binding(3) var<storage, read> v: array<f32>;
@group(0) @binding(4) var<storage, read_write> output: array<f32>;

fn score_pairwise(base: u32) -> f32 {
  let p0 = q[0u] * k[base + 0u] + q[1u] * k[base + 1u];
  let p1 = q[2u] * k[base + 2u] + q[3u] * k[base + 3u];
  let p2 = q[4u] * k[base + 4u] + q[5u] * k[base + 5u];
  let p3 = q[6u] * k[base + 6u] + q[7u] * k[base + 7u];
  return ((p0 + p1) + (p2 + p3)) * params.scale;
}

@compute @workgroup_size(1)
fn main() {
  let score0 = score_pairwise(0u);
  let score1 = score_pairwise(8u);
  let score2 = score_pairwise(16u);
  let score3 = score_pairwise(24u);
  let score4 = score_pairwise(32u);
  let score5 = score_pairwise(40u);
  let score6 = score_pairwise(48u);
  let score7 = score_pairwise(56u);

  let row_max = max(max(max(score0, score1), max(score2, score3)), max(max(score4, score5), max(score6, score7)));

  let exp0 = exp(clamp(score0 - row_max, -30.0, 30.0));
  let exp1 = exp(clamp(score1 - row_max, -30.0, 30.0));
  let exp2 = exp(clamp(score2 - row_max, -30.0, 30.0));
  let exp3 = exp(clamp(score3 - row_max, -30.0, 30.0));
  let exp4 = exp(clamp(score4 - row_max, -30.0, 30.0));
  let exp5 = exp(clamp(score5 - row_max, -30.0, 30.0));
  let exp6 = exp(clamp(score6 - row_max, -30.0, 30.0));
  let exp7 = exp(clamp(score7 - row_max, -30.0, 30.0));

  let total = ((exp0 + exp1) + (exp2 + exp3)) + ((exp4 + exp5) + (exp6 + exp7));

  let prob0 = exp0 / total;
  let prob1 = exp1 / total;
  let prob2 = exp2 / total;
  let prob3 = exp3 / total;
  let prob4 = exp4 / total;
  let prob5 = exp5 / total;
  let prob6 = exp6 / total;
  let prob7 = exp7 / total;

  let out0a = (prob0 * v[0u] + prob1 * v[2u]) + (prob2 * v[4u] + prob3 * v[6u]);
  let out0b = (prob4 * v[8u] + prob5 * v[10u]) + (prob6 * v[12u] + prob7 * v[14u]);
  let out1a = (prob0 * v[1u] + prob1 * v[3u]) + (prob2 * v[5u] + prob3 * v[7u]);
  let out1b = (prob4 * v[9u] + prob5 * v[11u]) + (prob6 * v[13u] + prob7 * v[15u]);

  output[0u] = out0a + out0b;
  output[1u] = out1a + out1b;
}
