struct Pair { a: u32, b: u32 }
      @group(0) @binding(0) var<storage, read_write> data: array<u32>;
      @compute @workgroup_size(1) fn main() {
        var pair = Pair(3u, 4u);
        let pairPtr = &pair;
        (*pairPtr).b += 2u;
        var values = array<u32, 3>(5u, 6u, 7u);
        var index = 1u;
        let elementPtr = &values[index];
        index = 2u;
        *elementPtr += 4u;
        data[0] = values[1u];
        data[1] = values[2u];
        data[2] = pair.b;
      }