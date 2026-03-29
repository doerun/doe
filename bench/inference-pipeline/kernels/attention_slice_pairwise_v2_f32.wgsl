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

@compute @workgroup_size(1)
fn main() {
  let score0 = (((q[0u] * k[0u] + q[1u] * k[1u]) + (q[2u] * k[2u] + q[3u] * k[3u])) +
    ((q[4u] * k[4u] + q[5u] * k[5u]) + (q[6u] * k[6u] + q[7u] * k[7u]))) * params.scale;
  let score1 = (((q[0u] * k[8u] + q[1u] * k[9u]) + (q[2u] * k[10u] + q[3u] * k[11u])) +
    ((q[4u] * k[12u] + q[5u] * k[13u]) + (q[6u] * k[14u] + q[7u] * k[15u]))) * params.scale;
  let score2 = (((q[0u] * k[16u] + q[1u] * k[17u]) + (q[2u] * k[18u] + q[3u] * k[19u])) +
    ((q[4u] * k[20u] + q[5u] * k[21u]) + (q[6u] * k[22u] + q[7u] * k[23u]))) * params.scale;
  let score3 = (((q[0u] * k[24u] + q[1u] * k[25u]) + (q[2u] * k[26u] + q[3u] * k[27u])) +
    ((q[4u] * k[28u] + q[5u] * k[29u]) + (q[6u] * k[30u] + q[7u] * k[31u]))) * params.scale;
  let score4 = (((q[0u] * k[32u] + q[1u] * k[33u]) + (q[2u] * k[34u] + q[3u] * k[35u])) +
    ((q[4u] * k[36u] + q[5u] * k[37u]) + (q[6u] * k[38u] + q[7u] * k[39u]))) * params.scale;
  let score5 = (((q[0u] * k[40u] + q[1u] * k[41u]) + (q[2u] * k[42u] + q[3u] * k[43u])) +
    ((q[4u] * k[44u] + q[5u] * k[45u]) + (q[6u] * k[46u] + q[7u] * k[47u]))) * params.scale;
  let score6 = (((q[0u] * k[48u] + q[1u] * k[49u]) + (q[2u] * k[50u] + q[3u] * k[51u])) +
    ((q[4u] * k[52u] + q[5u] * k[53u]) + (q[6u] * k[54u] + q[7u] * k[55u]))) * params.scale;
  let score7 = (((q[0u] * k[56u] + q[1u] * k[57u]) + (q[2u] * k[58u] + q[3u] * k[59u])) +
    ((q[4u] * k[60u] + q[5u] * k[61u]) + (q[6u] * k[62u] + q[7u] * k[63u]))) * params.scale;

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
