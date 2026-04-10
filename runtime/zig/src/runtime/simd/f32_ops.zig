const std = @import("std");

pub const F32_LANES: usize = 8;
const F32Vec = @Vector(F32_LANES, f32);

fn loadF32VectorFromF64(source: []const f64, start: usize) F32Vec {
    var scalars: [F32_LANES]f32 = undefined;
    inline for (0..F32_LANES) |lane| {
        scalars[lane] = @floatCast(source[start + lane]);
    }
    return @bitCast(scalars);
}

fn reduceAdd(value: F32Vec) f32 {
    var sum: f32 = 0;
    inline for (0..F32_LANES) |lane| {
        sum += value[lane];
    }
    return sum;
}

pub fn dotF64Scalar(lhs: []const f64, rhs: []const f64) f32 {
    var sum: f32 = 0;
    var index: usize = 0;
    while (index < lhs.len and index < rhs.len) : (index += 1) {
        sum += @as(f32, @floatCast(lhs[index])) * @as(f32, @floatCast(rhs[index]));
    }
    return sum;
}

pub fn dotF64(lhs: []const f64, rhs: []const f64) f32 {
    if (lhs.len < F32_LANES or rhs.len < F32_LANES) return dotF64Scalar(lhs, rhs);
    var index: usize = 0;
    var acc: F32Vec = @splat(0);
    while (index + F32_LANES <= lhs.len and index + F32_LANES <= rhs.len) : (index += F32_LANES) {
        const left = loadF32VectorFromF64(lhs, index);
        const right = loadF32VectorFromF64(rhs, index);
        acc += left * right;
    }

    var sum = reduceAdd(acc);
    sum += dotF64Scalar(lhs[index..], rhs[index..]);
    return sum;
}

pub fn sumF64Scalar(values: []const f64) f32 {
    var sum: f32 = 0;
    for (values) |value| {
        sum += @as(f32, @floatCast(value));
    }
    return sum;
}

pub fn sumF64(values: []const f64) f32 {
    if (values.len < F32_LANES) return sumF64Scalar(values);
    var index: usize = 0;
    var acc: F32Vec = @splat(0);
    while (index + F32_LANES <= values.len) : (index += F32_LANES) {
        acc += loadF32VectorFromF64(values, index);
    }

    var sum = reduceAdd(acc);
    sum += sumF64Scalar(values[index..]);
    return sum;
}

test "dotF64 matches scalar f32 accumulation on aligned tails" {
    const testing = std.testing;
    const lhs = [_]f64{ 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0 };
    const rhs = [_]f64{ 0.5, 1.5, 0.25, 2.0, 1.0, 0.5, 0.25, 0.125, 3.0 };
    var scalar: f32 = 0;
    for (lhs, rhs) |left, right| {
        scalar += @as(f32, @floatCast(left)) * @as(f32, @floatCast(right));
    }
    try testing.expectEqual(scalar, dotF64(&lhs, &rhs));
}

test "sumF64 matches scalar f32 accumulation" {
    const testing = std.testing;
    const values = [_]f64{ 1.0, -2.0, 3.5, 4.25, 5.0, -1.0, 0.5, 8.0, 16.0 };
    var scalar: f32 = 0;
    for (values) |value| scalar += @as(f32, @floatCast(value));
    try testing.expectEqual(scalar, sumF64(&values));
}
