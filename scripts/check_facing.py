"""Check which way each locomotion row faces, and that the two rows mirror."""

from __future__ import annotations

import os

import numpy as np
from PIL import Image

RUN = r"C:\Users\赵紫阳\.codex\visualizations\2026\09\14\01a0a048-aa99-7151-906a-1714b42c5616\wilson"
ATLAS = os.path.join(RUN, "final", "spritesheet-extended.webp")
W, H = 192, 208


def face_side(img, row, col=0):
    a = np.asarray(img.crop((col * W, row * H, (col + 1) * W, (row + 1) * H))).astype(np.float32)
    alpha = a[:, :, 3] > 200
    lum = a[:, :, :3].mean(axis=2)
    head = alpha.copy()
    head[110:, :] = False
    dark = head & (lum < 100)      # hair mass
    light = head & (lum >= 140)    # face / skin
    _, xs = np.nonzero(dark)
    _, xs2 = np.nonzero(light)
    if len(xs) == 0 or len(xs2) == 0:
        return None
    hair_x, face_x = xs.mean(), xs2.mean()
    return hair_x, face_x, ("RIGHT" if face_x > hair_x else "LEFT")


def main():
    im = Image.open(ATLAS).convert("RGBA")
    for row, label in [(0, "idle"), (1, "running-right"), (2, "running-left"),
                       (3, "waving"), (4, "hover(row4)")]:
        res = face_side(im, row)
        if res:
            hair_x, face_x, side = res
            print(f"row {row} {label:14s} hair_x={hair_x:6.1f} face_x={face_x:6.1f} -> faces {side}")
    a1 = np.asarray(im.crop((0, 1 * H, W, 2 * H))).astype(np.int16)
    a2 = np.asarray(im.crop((0, 2 * H, W, 3 * H)))[:, ::-1].astype(np.int16)
    print("row1 vs mirrored row2 max abs diff:", int(np.abs(a1 - a2).max()))


if __name__ == "__main__":
    main()
