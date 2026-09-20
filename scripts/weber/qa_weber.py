"""Objective QA for the Weber atlas: locomotion facing, mirroring, and the
16 look directions (white-eye feature displacement vs the neutral cell)."""

from __future__ import annotations

import json
import math
import os

import numpy as np
from PIL import Image

RUN = r"C:\Users\赵紫阳\.codex\visualizations\2026\09\20\01a0bcff-6673-7410-b0a9-ad1c84270d1d\weber"
ATLAS = os.path.join(RUN, "final", "spritesheet-extended.webp")
CELL_W, CELL_H = 192, 208

LOOK_A = [0, 22.5, 45, 67.5, 90, 112.5, 135, 157.5]
LOOK_B = [180, 202.5, 225, 247.5, 270, 292.5, 315, 337.5]


def cell(img, row, col):
    return img.crop((col * CELL_W, row * CELL_H, (col + 1) * CELL_W, (row + 1) * CELL_H))


def facing_of(img):
    """Weber faces the side his red mouth is on."""
    a = np.asarray(img).astype(np.float32)
    alpha = a[:, :, 3] > 200
    r, g, b = a[:, :, 0], a[:, :, 1], a[:, :, 2]
    head = alpha.copy()
    head[120:, :] = False
    mouth = head & (r > 150) & (g < 130) & (b < 130)
    body = head & (r < 90) & (g < 90) & (b < 90)
    _, m_x = np.nonzero(mouth)
    _, b_x = np.nonzero(body)
    if len(m_x) == 0 or len(b_x) == 0:
        return None
    mouth_x, body_x = m_x.mean(), b_x.mean()
    return mouth_x, body_x, ("RIGHT" if mouth_x > body_x else "LEFT")


def eye_feature_map(img):
    """Brightness of the head band: Weber's white eye circles are the landmark."""
    a = np.asarray(img).astype(np.float32)
    alpha = a[:, :, 3] > 200
    lum = a[:, :, :3].mean(axis=2)
    feat = np.where(alpha & (lum >= 180), lum, 0.0)
    mask = np.zeros(feat.shape, dtype=bool)
    mask[15:115, 30:162] = True
    return np.where(mask, feat, 0.0)


def best_shift(ref, other, radius=24):
    best = None
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            shifted = np.roll(np.roll(other, dy, axis=0), dx, axis=1)
            err = float(((shifted - ref) ** 2).sum())
            if best is None or err < best[0]:
                best = (err, dx, dy)
    return best[1], best[2]


def main() -> None:
    im = Image.open(ATLAS).convert("RGBA")
    report = {"facing": {}, "gaze": []}

    for row, label in [(1, "running-right"), (2, "running-left"),
                       (3, "waving"), (4, "hover")]:
        res = facing_of(cell(im, row, 0))
        if res:
            mouth_x, body_x, side = res
            report["facing"][f"row{row}"] = {
                "mouth_x": round(float(mouth_x), 1),
                "head_x": round(float(body_x), 1),
                "faces": side,
            }
            print(f"row {row}: mouth_x={mouth_x:6.1f} body_x={body_x:6.1f} -> {side}")

    a1 = np.asarray(im.crop((0, CELL_H, CELL_W, 2 * CELL_H))).astype(np.int16)
    a2 = np.asarray(im.crop((0, 2 * CELL_H, CELL_W, 3 * CELL_H)))[:, ::-1].astype(np.int16)
    diff = int(np.abs(a1 - a2).max())
    report["mirror_max_abs_diff"] = diff
    print("row1 vs mirrored row2 max abs diff:", diff)

    neutral = cell(im, 0, 6)
    ref = eye_feature_map(neutral)
    n = int((ref > 40).sum())
    for i, deg in enumerate(LOOK_A):
        dx, dy = best_shift(ref, eye_feature_map(cell(im, 9, i)))
        report["gaze"].append({"direction": deg, "row": 9, "col": i,
                               "dx": dx, "dy": dy, "pixels": n})
    for i, deg in enumerate(LOOK_B):
        dx, dy = best_shift(ref, eye_feature_map(cell(im, 10, i)))
        report["gaze"].append({"direction": deg, "row": 10, "col": i,
                               "dx": dx, "dy": dy, "pixels": n})

    verdicts = []
    for rec in report["gaze"]:
        deg = rec["direction"]
        name = {0: "up", 90: "screen-right", 180: "down", 270: "screen-left"}.get(deg)
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
                             "reason": f"white-eye features moved {cdx:+d}px x, "
                                       f"{cdy:+d}px y (angle error {err:.1f} deg)"})
        else:
            verdicts.append({"direction": f"{deg:g}", "expected": "intermediate",
                             "verdict": "pass" if err <= 34 else "warning",
                             "observed_angle": round(angle, 1),
                             "reason": f"white-eye features moved {cdx:+d}px x, "
                                       f"{cdy:+d}px y (angle error {err:.1f} deg)"})
        print(f"deg {deg:6.1f} dx={cdx:+3d} dy={cdy:+3d} angle={angle:6.1f} err={err:5.1f} "
              f"-> {verdicts[-1]['verdict']}")
    report["verdicts"] = verdicts
    report["problems"] = [v["direction"] for v in verdicts if v["verdict"] == "fail"]
    report["warnings"] = [v["direction"] for v in verdicts if v["verdict"] == "warning"]
    with open(os.path.join(RUN, "qa", "direction-evidence.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
    with open(os.path.join(RUN, "qa", "direction-semantics.json"), "w", encoding="utf-8") as fh:
        json.dump({"method": "white-eye SSD alignment against the neutral cell (row 0 col 6)",
                   "neutral_feature_pixels": n,
                   "cells": report["gaze"], "verdicts": verdicts},
                  fh, indent=2, ensure_ascii=False)
    print("failing cardinals:", report["problems"] or "none")
    print("warnings:", len(report["warnings"]))


if __name__ == "__main__":
    main()
