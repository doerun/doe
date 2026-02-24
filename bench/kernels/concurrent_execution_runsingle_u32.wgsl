const kBufferSize : u32 = 1024u;

@group(0) @binding(0) var<storage, read_write> inout_data : array<u32, kBufferSize>;
var<workgroup> wg_data : array<u32, kBufferSize>;

@compute @workgroup_size(1, 1, 1)
fn main() {
  var accum : u32 = inout_data[0];

  var i : u32 = 0u;
  loop {
    if (i >= kBufferSize) {
      break;
    }
    wg_data[i] = inout_data[i];
    i = i + 1u;
  }

  i = 0u;
  loop {
    if (i >= 1000000u) {
      break;
    }
    let idx = (i + accum) % kBufferSize;
    accum = (accum ^ wg_data[idx]) + 123u;
    i = i + 1u;
  }

  inout_data[0] = accum;
}
