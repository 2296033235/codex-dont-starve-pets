"""Extract Wilson's official art from the local Don't Starve / DST installs.

Decodes the KTEX atlases, splits the atlas into its individual sprite parts by
connected-component labelling, and writes a contact sheet plus a colour palette
that later generation steps use as grounding.
"""

from __future__ import annotations

import json
import os
import sys
import zipfile
from collections import deque

import numpy as np
from PIL import Image

RUN = r"C:\Users\赵紫阳\.codex\visualizations\2026\09\14\01a0a048-aa99-7151-906a-1714b42c5616\wilson"
sys.path.insert(0, os.path.join(RUN, "official"))
import ktex  # noqa: E402

DS = r"E:\SteamLibrary\steamapps\common\dont_starve"
DST = r"E:\SteamLibrary\steamapps\common\Don't Starve Together"
OUT = os.path.join(RUN, "official")


def read_zip_tex(zip_path: str, member: str) -> bytes:
    with zipfile.ZipFile(zip_path) as z:
        return z.read(member)


def label_components(mask: np.ndarray, min_pixels: int = 24):
    """Simple 4-connected component labelling with a Python BFS."""
    h, w = mask.shape
    seen = np.zeros_like(mask, dtype=bool)
    boxes = []
    for y0 in range(h):
        row = mask[y0]
        if not row.any():
            continue
        for x0 in np.nonzero(row & ~seen[y0])[0]:
            if seen[y0, x0]:
                continue
            q = deque([(y0, x0)])
            seen[y0, x0] = True
            minx = maxx = x0
            miny = maxy = y0
            count = 0
            while q:
                y, x = q.popleft()
                count += 1
                minx, maxx = min(minx, x), max(maxx, x)
                miny, maxy = min(miny, y), max(maxy, y)
                for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
                    if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not seen[ny, nx]:
                        seen[ny, nx] = True
                        q.append((ny, nx))
            if count >= min_pixels:
                boxes.append({"x": int(minx), "y": int(miny), "w": int(maxx - minx + 1),
                              "h": int(maxy - miny + 1), "pixels": int(count)})
    return boxes


def palette_of(img: np.ndarray, top: int = 24):
    alpha = img[:, :, 3]
    px = img[alpha > 200][:, :3]
    if len(px) == 0:
        return []
    # quantise to 8 levels/channel so near-identical shades merge
    q = (px // 8).astype(np.int32)
    keys, counts = np.unique(q[:, 0] * 1024 + q[:, 1] * 32 + q[:, 2], return_counts=True)
    order = np.argsort(-counts)[:top]
    out = []
    for i in order:
        key = keys[i]
        sel = px[(q[:, 0] * 1024 + q[:, 1] * 32 + q[:, 2]) == key]
        colour = sel.mean(axis=0).round().astype(int).tolist()
        out.append({"rgb": colour, "count": int(counts[i]),
                    "share": round(float(counts[i]) / len(px), 4)})
    return out


def main():
    os.makedirs(os.path.join(OUT, "parts_ds"), exist_ok=True)
    os.makedirs(os.path.join(OUT, "parts_dst"), exist_ok=True)
    report = {}

    for tag, root in (("ds", DS), ("dst", DST)):
        zip_path = os.path.join(root, "data", "anim", "wilson.zip")
        if not os.path.exists(zip_path):
            print(f"missing {zip_path}")
            continue
        data = read_zip_tex(zip_path, "atlas-0.tex")
        img = ktex.decode_mipmap(data, 0)
        img = img[::-1, :]  # KTEX payloads are stored bottom-up
        name = f"wilson_atlas_{tag}.png"
        Image.fromarray(img, "RGBA").save(os.path.join(OUT, name))
        pal = palette_of(img)
        boxes = label_components(img[:, :, 3] > 8)
        boxes.sort(key=lambda b: (b["y"] // 24, b["x"]))
        part_dir = os.path.join(OUT, f"parts_{tag}")
        manifest = []
        for i, b in enumerate(boxes):
            crop = img[b["y"]: b["y"] + b["h"], b["x"]: b["x"] + b["w"]]
            fn = f"part_{i:03d}.png"
            Image.fromarray(crop, "RGBA").save(os.path.join(part_dir, fn))
            manifest.append({**b, "file": fn})
        with open(os.path.join(part_dir, "manifest.json"), "w", encoding="utf-8") as fh:
            json.dump(manifest, fh, indent=2)
        with open(os.path.join(OUT, f"palette_{tag}.json"), "w", encoding="utf-8") as fh:
            json.dump(pal, fh, indent=2)

        # contact sheet of parts
        cols = 14
        cell = 132
        rows = (len(boxes) + cols - 1) // cols
        sheet = Image.new("RGB", (cols * cell, rows * cell), (255, 0, 255))
        for i, b in enumerate(boxes):
            crop = Image.fromarray(img[b["y"]: b["y"] + b["h"], b["x"]: b["x"] + b["w"]], "RGBA")
            scale = min((cell - 10) / max(1, crop.width), (cell - 10) / max(1, crop.height))
            crop = crop.resize((max(1, int(crop.width * scale)), max(1, int(crop.height * scale))), Image.LANCZOS)
            cx, cy = (i % cols) * cell, (i // cols) * cell
            sheet.paste(crop, (cx + (cell - crop.width) // 2, cy + (cell - crop.height) // 2), crop)
        sheet.save(os.path.join(OUT, f"parts_contact_{tag}.png"))

        report[tag] = {"atlas": name, "parts": len(boxes), "palette_top": pal[:8],
                       "size": [img.shape[1], img.shape[0]]}
        print(f"{tag}: atlas {img.shape[1]}x{img.shape[0]}, parts={len(boxes)}")
        print(f"   palette: {[p['rgb'] for p in pal[:8]]}")

    with open(os.path.join(OUT, "extraction_report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)


if __name__ == "__main__":
    main()
