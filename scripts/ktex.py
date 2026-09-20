"""Pure-Python decoder for Klei's KTEX texture container (Don't Starve / DST).

Layout (reverse engineered from the GPL `ktech` tool by "simplex", and verified
against a mod's .tex/.png pair):

    'KTEX'
    u32 bitfield:
        bits  0- 3  platform        (0 default, 10 PS3, 11 X360, 12 PC)
        bits  4- 8  compression     (0 DXT1, 1 DXT3, 2 DXT5, 4 RGBA, 5 RGB)
        bits  9-12  texture type    (0 1D, 1 2D, 2 3D, 3 cube)
        bits 13-17  mipmap count
        bits 18-19  flags
        bits 20-31  fill (0xFFF)
    then, for every mip level:  u16 width, u16 height, u16 pitch, u32 data size
    then the raw payload of every mip level, in order.

Payload blocks are standard S3TC (squish): DXT5 is 8 bytes of alpha followed by
8 bytes of BC1 colour per 4x4 tile.

Usage:
    python ktex.py <file.tex> <out.png> [--mip N] [--info]
"""

from __future__ import annotations

import argparse
import os
import struct
import sys

import numpy as np
from PIL import Image

KTEX_MAGIC = b"KTEX"


# --------------------------------------------------------------------------- #
# header / mip helpers
# --------------------------------------------------------------------------- #
COMPRESSION = {0: "DXT1", 1: "DXT3", 2: "DXT5", 4: "RGBA", 5: "RGB"}
PLATFORM = {0: "Default", 10: "PS3", 11: "Xbox 360", 12: "PC"}
TEXTURE_TYPE = {0: "1D", 1: "2D", 2: "3D", 3: "Cube"}


def parse_header(data: bytes):
    """Parse the 8-byte KTEX header into its bitfields."""
    if data[:4] != KTEX_MAGIC:
        raise ValueError("not a KTEX file")
    bits = struct.unpack_from("<I", data, 4)[0]
    header = {
        "platform": bits & 0xF,
        "compression": (bits >> 4) & 0x1F,
        "texture_type": (bits >> 9) & 0xF,
        "mipmap_count": (bits >> 13) & 0x1F,
        "flags": (bits >> 18) & 0x3,
        "fill": (bits >> 20) & 0xFFF,
        "raw": bits,
    }
    header["platform_name"] = PLATFORM.get(header["platform"], str(header["platform"]))
    header["compression_name"] = COMPRESSION.get(header["compression"], str(header["compression"]))
    header["texture_type_name"] = TEXTURE_TYPE.get(header["texture_type"], str(header["texture_type"]))
    return header


def read_mipmaps(data: bytes):
    """Return [{'width','height','pitch','size','offset'}, ...] for every mip."""
    header = parse_header(data)
    count = header["mipmap_count"]
    table_end = 8 + count * 10
    mips = []
    offset = table_end
    for i in range(count):
        base = 8 + i * 10
        width, height, pitch = struct.unpack_from("<HHH", data, base)
        (size,) = struct.unpack_from("<I", data, base + 6)
        mips.append(
            {
                "width": width,
                "height": height,
                "pitch": pitch,
                "size": size,
                "offset": offset,
            }
        )
        offset += size
    return mips


def describe(path: str) -> str:
    data = open(path, "rb").read()
    header = parse_header(data)
    mips = read_mipmaps(data)
    lines = [
        f"{os.path.basename(path)}: {len(data)} bytes",
        f"  platform={header['platform_name']} compression={header['compression_name']}"
        f" type={header['texture_type_name']} mips={header['mipmap_count']} flags={header['flags']}",
        f"  mip0 {mips[0]['width']}x{mips[0]['height']} pitch={mips[0]['pitch']}"
        f" size={mips[0]['size']} offset={mips[0]['offset']}",
    ]
    return "\n".join(lines)


def mip_levels(width: int, height: int, block_bytes: int = 16):
    """Return [(w, h, byte_size), ...] for the full mip chain."""
    out = []
    w, h = width, height
    while True:
        blocks = max(1, (w + 3) // 4) * max(1, (h + 3) // 4)
        out.append((w, h, blocks * block_bytes))
        if w == 1 and h == 1:
            break
        w = max(1, w // 2)
        h = max(1, h // 2)
    return out


# --------------------------------------------------------------------------- #
# block codecs
# --------------------------------------------------------------------------- #
def _bits(bytearr: np.ndarray) -> np.ndarray:
    """Expand bytes to a little-endian bit array; last axis becomes bits."""
    b = (bytearr[..., None] >> np.arange(8, dtype=np.uint8)) & 1
    return b.astype(np.uint16).reshape(b.shape[:-2] + (-1,))


def bc3_alpha(data: bytes, block_w: int, block_h: int) -> np.ndarray:
    """Decode the BC3/DXT5 alpha half. Returns float alpha in [0, 255]."""
    blocks = np.frombuffer(data, dtype=np.uint8, count=block_w * block_h * 8)
    blocks = blocks.reshape(block_h, block_w, 8)
    a0 = blocks[:, :, 0].astype(np.float32)
    a1 = blocks[:, :, 1].astype(np.float32)
    bits = _bits(blocks[:, :, 2:8]).reshape(block_h, block_w, 16, 3)
    idx = bits[..., 0] | (bits[..., 1] << 1) | (bits[..., 2] << 2)
    big = a0 > a1
    table = np.zeros((block_h, block_w, 8), dtype=np.float32)
    table[:, :, 0] = a0
    table[:, :, 1] = a1
    # 8-value mode (a0 > a1): six interpolated steps at 6/7 .. 1/7.
    # 6-value mode (a0 <= a1): four interpolated steps at 4/5 .. 1/5,
    # then index 6 -> 0 and index 7 -> 255.
    for i in range(1, 7):
        w = i / 7.0
        table[:, :, i + 1] = np.where(big, a0 * (1.0 - w) + a1 * w, 0.0)
    for i in range(1, 5):
        w = i / 5.0
        table[:, :, i + 1] = np.where(big, table[:, :, i + 1], a0 * (1.0 - w) + a1 * w)
    table[:, :, 7] = np.where(big, table[:, :, 7], 255.0)
    return np.take_along_axis(table, idx, axis=2)


def bc1_color(data: bytes, block_w: int, block_h: int):
    """Decode a BC1/DXT1 color half. Returns (rgb float [0,255], opaque mask)."""
    blocks = np.frombuffer(data, dtype=np.uint8, count=block_w * block_h * 8)
    blocks = blocks.reshape(block_h, block_w, 8)
    c0 = blocks[:, :, 0].astype(np.uint16) | (blocks[:, :, 1].astype(np.uint16) << 8)
    c1 = blocks[:, :, 2].astype(np.uint16) | (blocks[:, :, 3].astype(np.uint16) << 8)

    def unpack(v):
        r = ((v >> 11) & 31).astype(np.float32) * (255.0 / 31.0)
        g = ((v >> 5) & 63).astype(np.float32) * (255.0 / 63.0)
        b = (v & 31).astype(np.float32) * (255.0 / 31.0)
        return r, g, b

    r0, g0, b0 = unpack(c0)
    r1, g1, b1 = unpack(c1)
    bits = _bits(blocks[:, :, 4:8]).reshape(block_h, block_w, 16, 2)
    idx = bits[..., 0] | (bits[..., 1] << 1)
    big = (c0 > c1)[..., None]
    r2 = np.where(big, (2 * r0[..., None] + r1[..., None]) / 3.0, (r0[..., None] + r1[..., None]) / 2.0)
    g2 = np.where(big, (2 * g0[..., None] + g1[..., None]) / 3.0, (g0[..., None] + g1[..., None]) / 2.0)
    b2 = np.where(big, (2 * b0[..., None] + b1[..., None]) / 3.0, (b0[..., None] + b1[..., None]) / 2.0)
    r3 = np.where(big, (r0[..., None] + 2 * r1[..., None]) / 3.0, 0.0)
    g3 = np.where(big, (g0[..., None] + 2 * g1[..., None]) / 3.0, 0.0)
    b3 = np.where(big, (b0[..., None] + 2 * b1[..., None]) / 3.0, 0.0)
    rs = np.concatenate([r0[..., None], r1[..., None], r2, r3], axis=2)
    gs = np.concatenate([g0[..., None], g1[..., None], g2, g3], axis=2)
    bs = np.concatenate([b0[..., None], b1[..., None], b2, b3], axis=2)
    rgb = np.stack(
        [
            np.take_along_axis(rs, idx, axis=2),
            np.take_along_axis(gs, idx, axis=2),
            np.take_along_axis(bs, idx, axis=2),
        ],
        axis=3,
    )
    opaque = np.where(idx == 3, np.where(big, 1.0, 0.0), 1.0)[..., 0]
    return rgb, opaque


def _assemble(rgb: np.ndarray, alpha: np.ndarray, block_w: int, block_h: int) -> np.ndarray:
    """Turn per-block 4x4 tiles into a (h, w, 4) uint8 image."""
    h, w = block_h * 4, block_w * 4
    rgba = np.concatenate([rgb, alpha[..., None]], axis=3)
    return (
        rgba.reshape(block_h, block_w, 4, 4, 4)
        .transpose(0, 2, 1, 3, 4)
        .reshape(h, w, 4)
        .clip(0, 255)
        .astype(np.uint8)
    )


def decode_mip(data: bytes, offset: int, width: int, height: int, mode: str) -> np.ndarray:
    """Decode one mip level. ``mode`` selects the payload layout."""
    bw = max(1, (width + 3) // 4)
    bh = max(1, (height + 3) // 4)
    n = bw * bh
    half = n * 8

    if mode in ("dxt5_color_first", "dxt5_alpha_first"):
        raw = data[offset : offset + n * 16]
        blocks = np.frombuffer(raw, dtype=np.uint8, count=n * 16).reshape(n, 16)
        if mode == "dxt5_color_first":
            color_bytes = np.ascontiguousarray(blocks[:, :8]).tobytes()
            alpha_bytes = np.ascontiguousarray(blocks[:, 8:]).tobytes()
        else:
            alpha_bytes = np.ascontiguousarray(blocks[:, :8]).tobytes()
            color_bytes = np.ascontiguousarray(blocks[:, 8:]).tobytes()
        alpha = bc3_alpha(alpha_bytes, bw, bh)
        rgb, _opaque = bc1_color(color_bytes, bw, bh)
        return _assemble(rgb, alpha, bw, bh)

    if mode == "planar_alpha_first":
        alpha = bc3_alpha(data[offset : offset + half], bw, bh)
        rgb, _opaque = bc1_color(data[offset + half : offset + 2 * half], bw, bh)
        return _assemble(rgb, alpha, bw, bh)

    if mode == "planar_color_first":
        rgb, _opaque = bc1_color(data[offset : offset + half], bw, bh)
        alpha = bc3_alpha(data[offset + half : offset + 2 * half], bw, bh)
        return _assemble(rgb, alpha, bw, bh)

    raise ValueError(f"unknown mode {mode!r}")


MODES = ("dxt5_color_first", "dxt5_alpha_first", "planar_alpha_first", "planar_color_first")


def decode_mipmap(data: bytes, index: int = 0) -> np.ndarray:
    """Decode one mip level of a KTEX file to an (h, w, 4) uint8 array."""
    header = parse_header(data)
    mips = read_mipmaps(data)
    mip = mips[index]
    w, h = mip["width"], mip["height"]
    payload = data[mip["offset"] : mip["offset"] + mip["size"]]
    bw, bh = max(1, (w + 3) // 4), max(1, (h + 3) // 4)
    n = bw * bh
    fmt = header["compression"]

    if fmt == 2:  # DXT5: alpha block first, then BC1 colour block
        blocks = np.frombuffer(payload, dtype=np.uint8, count=n * 16).reshape(n, 16)
        alpha_bytes = np.ascontiguousarray(blocks[:, :8]).tobytes()
        color_bytes = np.ascontiguousarray(blocks[:, 8:]).tobytes()
        alpha = bc3_alpha(alpha_bytes, bw, bh)
        rgb, _ = bc1_color(color_bytes, bw, bh)
        return _assemble(rgb, alpha, bw, bh)

    if fmt == 0:  # DXT1
        rgb, opaque = bc1_color(payload[: n * 8], bw, bh)
        return _assemble(rgb, opaque * 255.0, bw, bh)

    if fmt == 4:  # raw RGBA
        arr = np.frombuffer(payload[: w * h * 4], dtype=np.uint8).reshape(h, w, 4)
        return arr.astype(np.uint8)

    if fmt == 5:  # raw RGB
        arr = np.frombuffer(payload[: w * h * 3], dtype=np.uint8).reshape(h, w, 3)
        rgba = np.concatenate([arr, np.full((h, w, 1), 255, dtype=np.uint8)], axis=2)
        return rgba

    raise ValueError(f"unsupported compression {header['compression_name']}")


# --------------------------------------------------------------------------- #
# scoring / probe
# --------------------------------------------------------------------------- #
def score_against(decoded: np.ndarray, reference: np.ndarray) -> float:
    """Mean absolute error of both images composited over white."""
    a = decoded.astype(np.float32) / 255.0
    b = reference.astype(np.float32) / 255.0
    comp_a = a[:, :, :3] * a[:, :, 3:4] + (1 - a[:, :, 3:4])
    comp_b = b[:, :, :3] * b[:, :, 3:4] + (1 - b[:, :, 3:4])
    return float(np.abs(comp_a - comp_b).mean() * 255.0)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("tex")
    ap.add_argument("out", nargs="?")
    ap.add_argument("--mip", type=int, default=0)
    ap.add_argument("--info", action="store_true")
    args = ap.parse_args(argv)

    data = open(args.tex, "rb").read()
    print(describe(args.tex))
    if args.info or not args.out:
        return 0
    img = decode_mipmap(data, args.mip)
    Image.fromarray(img, "RGBA").save(args.out)
    print(f"wrote {args.out} ({img.shape[1]}x{img.shape[0]})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
