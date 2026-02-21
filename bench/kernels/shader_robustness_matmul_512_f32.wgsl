alias ElemT = f32;

const K_TILE_SIZE: u32 = 32u;
const K_WORKGROUP_SIZE_X: u32 = 8u;
const K_WORKGROUP_SIZE_Y: u32 = 8u;

const K_DIM_A_OUTER: u32 = 512u;
const K_DIM_INNER: u32 = 512u;
const K_DIM_B_OUTER: u32 = 512u;

const ROW_PER_THREAD: u32 = K_TILE_SIZE / K_WORKGROUP_SIZE_Y;
const COL_PER_THREAD: u32 = K_TILE_SIZE / K_WORKGROUP_SIZE_X;
const NUM_TILES: u32 = (K_DIM_INNER - 1u) / K_TILE_SIZE + 1u;

@group(0) @binding(0) var<storage, read> first_matrix: array<ElemT>;
@group(0) @binding(1) var<storage, read> second_matrix: array<ElemT>;
@group(0) @binding(2) var<storage, read_write> result_matrix: array<ElemT>;

var<workgroup> mm_a_sub: array<ElemT, K_TILE_SIZE * K_TILE_SIZE>;
var<workgroup> mm_b_sub: array<ElemT, K_TILE_SIZE * K_TILE_SIZE>;

fn mm_read_a(row: u32, col: u32) -> ElemT {
  if (row < K_DIM_A_OUTER && col < K_DIM_INNER) {
    return first_matrix[row * K_DIM_INNER + col];
  }
  return 0.0;
}

fn mm_read_b(row: u32, col: u32) -> ElemT {
  if (row < K_DIM_INNER && col < K_DIM_B_OUTER) {
    return second_matrix[row * K_DIM_B_OUTER + col];
  }
  return 0.0;
}

fn mm_write(row: u32, col: u32, value: ElemT) {
  if (row < K_DIM_A_OUTER && col < K_DIM_B_OUTER) {
    result_matrix[col + row * K_DIM_B_OUTER] = value;
  }
}

@compute @workgroup_size(K_WORKGROUP_SIZE_X, K_WORKGROUP_SIZE_Y, 1)
fn main(
  @builtin(local_invocation_id) local_id: vec3u,
  @builtin(global_invocation_id) global_id: vec3u
) {
  let tile_row: u32 = local_id.y * ROW_PER_THREAD;
  let tile_col: u32 = local_id.x * COL_PER_THREAD;
  let global_row: u32 = global_id.y * ROW_PER_THREAD;
  let global_col: u32 = global_id.x * COL_PER_THREAD;

  var acc: array<ElemT, ROW_PER_THREAD * COL_PER_THREAD>;
  for (var i: u32 = 0u; i < ROW_PER_THREAD * COL_PER_THREAD; i = i + 1u) {
    acc[i] = 0.0;
  }

  let col_per_thread_a: u32 = K_TILE_SIZE / K_WORKGROUP_SIZE_X;
  let tile_col_a: u32 = local_id.x * col_per_thread_a;
  let row_per_thread_b: u32 = K_TILE_SIZE / K_WORKGROUP_SIZE_Y;
  let tile_row_b: u32 = local_id.y * row_per_thread_b;

  for (var t: u32 = 0u; t < NUM_TILES; t = t + 1u) {
    for (var inner_row: u32 = 0u; inner_row < ROW_PER_THREAD; inner_row = inner_row + 1u) {
      for (var inner_col: u32 = 0u; inner_col < col_per_thread_a; inner_col = inner_col + 1u) {
        let input_row: u32 = tile_row + inner_row;
        let input_col: u32 = tile_col_a + inner_col;
        let index: u32 = input_row * K_TILE_SIZE + input_col;
        mm_a_sub[index] = mm_read_a(global_row + inner_row, t * K_TILE_SIZE + input_col);
      }
    }

    for (var inner_row: u32 = 0u; inner_row < row_per_thread_b; inner_row = inner_row + 1u) {
      for (var inner_col: u32 = 0u; inner_col < COL_PER_THREAD; inner_col = inner_col + 1u) {
        let input_row: u32 = tile_row_b + inner_row;
        let input_col: u32 = tile_col + inner_col;
        let index: u32 = input_row * K_TILE_SIZE + input_col;
        mm_b_sub[index] = mm_read_b(t * K_TILE_SIZE + input_row, global_col + inner_col);
      }
    }

    workgroupBarrier();

    for (var k: u32 = 0u; k < K_TILE_SIZE; k = k + 1u) {
      var b_cached: array<ElemT, COL_PER_THREAD>;
      for (var inner: u32 = 0u; inner < COL_PER_THREAD; inner = inner + 1u) {
        b_cached[inner] = mm_b_sub[k * K_TILE_SIZE + tile_col + inner];
      }

      for (var inner_row: u32 = 0u; inner_row < ROW_PER_THREAD; inner_row = inner_row + 1u) {
        let a_cached: ElemT = mm_a_sub[(tile_row + inner_row) * K_TILE_SIZE + k];
        for (var inner_col: u32 = 0u; inner_col < COL_PER_THREAD; inner_col = inner_col + 1u) {
          let index: u32 = inner_row * COL_PER_THREAD + inner_col;
          acc[index] = acc[index] + a_cached * b_cached[inner_col];
        }
      }
    }

    workgroupBarrier();
  }

  for (var inner_row: u32 = 0u; inner_row < ROW_PER_THREAD; inner_row = inner_row + 1u) {
    for (var inner_col: u32 = 0u; inner_col < COL_PER_THREAD; inner_col = inner_col + 1u) {
      let index: u32 = inner_row * COL_PER_THREAD + inner_col;
      mm_write(global_row + inner_row, global_col + inner_col, acc[index]);
    }
  }
}
