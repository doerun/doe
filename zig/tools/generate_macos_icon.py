#!/usr/bin/env python3
"""Generate a deterministic macOS .icns icon for the Doe runtime app bundle."""

from __future__ import annotations

import argparse
import struct
import zlib
from pathlib import Path

ICNS_ENTRIES = (
    (16, b"icp4"),
    (32, b"icp5"),
    (64, b"icp6"),
    (128, b"ic07"),
    (256, b"ic08"),
    (512, b"ic09"),
    (1024, b"ic10"),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True, help="Output .icns path")
    return parser.parse_args()


def chunk(chunk_type: bytes, data: bytes) -> bytes:
    crc = zlib.crc32(chunk_type + data) & 0xFFFFFFFF
    return (
        struct.pack(">I", len(data))
        + chunk_type
        + data
        + struct.pack(">I", crc)
    )


def clamp_u8(value: int) -> int:
    if value < 0:
        return 0
    if value > 255:
        return 255
    return value


def make_icon_pixels(size: int) -> bytes:
    pixels = bytearray(size * size * 4)
    margin = max(1, size // 5)
    stroke = max(1, size // 10)
    stem_left = margin
    stem_right = stem_left + stroke
    top_bar_right = size - margin
    middle_y = (size // 2) - (stroke // 2)
    middle_bar_right = size - margin - (size // 5)

    for y in range(size):
        for x in range(size):
            nx = x / max(1, size - 1)
            ny = y / max(1, size - 1)

            # Deterministic teal gradient background with subtle diagonal shift.
            red = 14 + int(34 * nx) + int(9 * ny)
            green = 95 + int(90 * nx)
            blue = 120 + int(95 * (1.0 - ny))

            # Add a soft top-left highlight for better Finder legibility.
            dx = (x - (size * 0.30)) / max(1.0, size * 0.30)
            dy = (y - (size * 0.25)) / max(1.0, size * 0.30)
            dist2 = (dx * dx) + (dy * dy)
            if dist2 < 1.0:
                boost = int((1.0 - dist2) * 28)
                red += boost
                green += boost
                blue += boost

            draw_stem = (stem_left <= x < stem_right) and (margin <= y < size - margin)
            draw_top_bar = (stem_left <= x < top_bar_right) and (margin <= y < margin + stroke)
            draw_middle_bar = (stem_left <= x < middle_bar_right) and (middle_y <= y < middle_y + stroke)
            draw_letter = draw_stem or draw_top_bar or draw_middle_bar

            if draw_letter:
                red = 245
                green = 252
                blue = 255

            i = (y * size + x) * 4
            pixels[i + 0] = clamp_u8(red)
            pixels[i + 1] = clamp_u8(green)
            pixels[i + 2] = clamp_u8(blue)
            pixels[i + 3] = 255

    return bytes(pixels)


def encode_png_rgba(width: int, height: int, pixels: bytes) -> bytes:
    if len(pixels) != width * height * 4:
        raise ValueError("pixel buffer length mismatch")
    scanlines = bytearray()
    row_bytes = width * 4
    for row in range(height):
        scanlines.append(0)
        start = row * row_bytes
        scanlines.extend(pixels[start : start + row_bytes])
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(bytes(scanlines), level=9))
        + chunk(b"IEND", b"")
    )


def encode_icns() -> bytes:
    encoded_chunks = []
    for size, icns_type in ICNS_ENTRIES:
        png_data = encode_png_rgba(size, size, make_icon_pixels(size))
        encoded_chunks.append(icns_type + struct.pack(">I", len(png_data) + 8) + png_data)
    body = b"".join(encoded_chunks)
    return b"icns" + struct.pack(">I", len(body) + 8) + body


def main() -> int:
    args = parse_args()
    out_path = Path(args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(encode_icns())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
