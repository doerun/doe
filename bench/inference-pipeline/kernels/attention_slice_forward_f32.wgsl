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

fn score_forward(base: u32) -> f32 {
  var acc: f32 = 0.0;
  acc = acc + q[0u] * k[base + 0u];
  acc = acc + q[1u] * k[base + 1u];
  acc = acc + q[2u] * k[base + 2u];
  acc = acc + q[3u] * k[base + 3u];
  acc = acc + q[4u] * k[base + 4u];
  acc = acc + q[5u] * k[base + 5u];
  acc = acc + q[6u] * k[base + 6u];
  acc = acc + q[7u] * k[base + 7u];
  return acc * params.scale;
}

@compute @workgroup_size(1)
fn main() {
  let score0 = score_forward(0u);
  let score1 = score_forward(8u);
  let score2 = score_forward(16u);
  let score3 = score_forward(24u);
  let score4 = score_forward(32u);
  let score5 = score_forward(40u);
  let score6 = score_forward(48u);
  let score7 = score_forward(56u);

  let row_max = max(max(max(score0, score1), max(score2, score3)), max(max(score4, score5), max(score6, score7)));

  let exp0 = exp(clamp(score0 - row_max, -30.0, 30.0));
  let exp1 = exp(clamp(score1 - row_max, -30.0, 30.0));
  let exp2 = exp(clamp(score2 - row_max, -30.0, 30.0));
  let exp3 = exp(clamp(score3 - row_max, -30.0, 30.0));
  let exp4 = exp(clamp(score4 - row_max, -30.0, 30.0));
  let exp5 = exp(clamp(score5 - row_max, -30.0, 30.0));
  let exp6 = exp(clamp(score6 - row_max, -30.0, 30.0));
  let exp7 = exp(clamp(score7 - row_max, -30.0, 30.0));

  var total: f32 = 0.0;
  total = total + exp0;
  total = total + exp1;
  total = total + exp2;
  total = total + exp3;
  total = total + exp4;
  total = total + exp5;
  total = total + exp6;
  total = total + exp7;

  let prob0 = exp0 / total;
  let prob1 = exp1 / total;
  let prob2 = exp2 / total;
  let prob3 = exp3 / total;
  let prob4 = exp4 / total;
  let prob5 = exp5 / total;
  let prob6 = exp6 / total;
  let prob7 = exp7 / total;

  var out0: f32 = 0.0;
  out0 = out0 + prob0 * v[0u];
  out0 = out0 + prob1 * v[2u];
  out0 = out0 + prob2 * v[4u];
  out0 = out0 + prob3 * v[6u];
  out0 = out0 + prob4 * v[8u];
  out0 = out0 + prob5 * v[10u];
  out0 = out0 + prob6 * v[12u];
  out0 = out0 + prob7 * v[14u];

  var out1: f32 = 0.0;
  out1 = out1 + prob0 * v[1u];
  out1 = out1 + prob1 * v[3u];
  out1 = out1 + prob2 * v[5u];
  out1 = out1 + prob3 * v[7u];
  out1 = out1 + prob4 * v[9u];
  out1 = out1 + prob5 * v[11u];
  out1 = out1 + prob6 * v[13u];
  out1 = out1 + prob7 * v[15u];

  output[0u] = out0;
  output[1u] = out1;
}
