"""Objective gaze-cue measurement for the 16 look cells.

Measures where the dark facial features (eyes/pupils) sit inside the head
relative to the neutral cell, then checks the clockwise progression and the
four cardinal axes.
"""

from __future__ import annotations

import json
import math
import os

import numpy as np
from PIL import Image

RUN = r"C:\Users\赵紫阳\.codex\visualizations\2026\09\14\01a0a048-aa99-7151-906a-1714b42c5616\wilson"
ATLAS = os.path.join(RUN, "final", "spritesheet-extended.webp")
CELL_W, CELL_H = 192, 208

LOOK_A = [0, 22.5, 45, 67.5, 90, 112.5, 135, 157.5]
LOOK_B = [180, 202.5, 225, 247.5, 270, 292.5, 315, 337.5]


def cell(atlas, row, col):
    return atlas.crop((col * CELL_W, row * CELL_H, (col + 1) * CELL_W, (row + 1) * CELL_H))


def head_feature_map(img):
    """Grayscale of the head region, using the facial features' dark pixels."""
    a = np.asarray(img).astype(np.float32)
    alpha = a[:, :, 3] > 200
    lum = a[:, :, :3].mean(axis=2)
    feat = np.where(alpha, 255.0 - lum, 0.0)   # bright where features are dark
    # keep the eye/brow band of the head only: the hair is a much larger dark
    # area and would otherwise dominate the alignment
    mask = np.zeros(feat.shape, dtype=bool)
    mask[22:100, 38:154] = True
    feat = np.where(mask, feat, 0.0)
    return feat


def best_shift(ref, other, radius=22):
    """Integer shift of `other` that best aligns it with `ref` (SSD)."""
    best = None
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            shifted = np.roll(np.roll(other, dy, axis=0), dx, axis=1)
            err = float(((shifted - ref) ** 2).sum())
            if best is None or err < best[0]:
                best = (err, dx, dy)
    return best[1], best[2]


def main():
    atlas = Image.open(ATLAS).convert("RGBA")
    neutral = cell(atlas, 0, 6)
    ref = head_feature_map(neutral)
    n_n = int((ref > 40).sum())

    records = []
    for i, deg in enumerate(LOOK_A):
        c = cell(atlas, 9, i)
        dx, dy = best_shift(ref, head_feature_map(c))
        records.append({"direction": deg, "row": 9, "col": i,
                        "dx": dx, "dy": dy, "pixels": n_n})
    for i, deg in enumerate(LOOK_B):
        c = cell(atlas, 10, i)
        dx, dy = best_shift(ref, head_feature_map(c))
        records.append({"direction": deg, "row": 10, "col": i,
                        "dx": dx, "dy": dy, "pixels": n_n})

    # expected axis sign for each cardinal
    expectations = {0: ("up", 0, -1), 90: ("screen-right", 1, 0),
                    180: ("down", 0, 1), 270: ("screen-left", -1, 0)}
    verdicts = []
    for rec in records:
        deg = rec["direction"]
        name = {0: "up", 90: "screen-right", 180: "down", 270: "screen-left"}.get(deg)
        # `best_shift` returns the shift that realigns the cell with the neutral,
        # so the feature displacement is the negation of it
        cdx = -(rec["dx"] or 0)
        cdy = -(rec["dy"] or 0)
        rec["feature_dx"] = cdx
        rec["feature_dy"] = cdy
        angle = math.degrees(math.atan2(cdx, -cdy)) % 360
        err = min(abs(angle - deg), 360 - abs(angle - deg))
        rec["measured_angle"] = round(angle, 1)
        rec["angle_error"] = round(err, 1)
        if name:
            ok = err <= 30
            verdicts.append({"direction": f"{deg:g}", "expected": name,
                             "verdict": "pass" if ok else "fail",
                             "observed_angle": round(angle, 1),
                             "reason": f"facial-feature centroid moved {rec['dx']:+.1f}px x, "
                                       f"{rec['dy']:+.1f}px y (angle error {err:.1f} deg)"})
        else:
            verdicts.append({"direction": f"{deg:g}", "expected": "intermediate",
                             "verdict": "pass" if err <= 34 else "warning",
                             "observed_angle": round(angle, 1),
                             "reason": f"centroid {rec['dx']:+.1f}px x, {rec['dy']:+.1f}px y "
                                       f"(angle error {err:.1f} deg)"})

    out = {"method": "head feature SSD alignment against the neutral cell (row 0 col 6)",
           "neutral_feature_pixels": n_n, "cells": records, "verdicts": verdicts}
    with open(os.path.join(RUN, "qa", "direction-semantics.json"), "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2, ensure_ascii=False)

    print(f"neutral feature pixels {n_n}")
    for rec in records:
        print(f"  {rec['direction']:6g} dx={rec['dx']:+7.2f} dy={rec['dy']:+7.2f} "
              f"angle={rec['measured_angle']:6.1f} err={rec['angle_error']:5.1f}")
    bad = [v for v in verdicts if v["verdict"] == "fail"]
    print("failing cardinals:", bad if bad else "none")
    print("warnings:", len([v for v in verdicts if v["verdict"] == "warning"]))


if __name__ == "__main__":
    main()
