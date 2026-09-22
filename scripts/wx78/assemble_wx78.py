"""Assemble the Codex v2 pet atlas (8x11, 192x208 cells) from official
Don't Starve animation frames for WX-78, plus a 16-pose look loop built from
the official head parts.  Run with --look-probe to render only the look
mechanics strip for tuning.
"""

from __future__ import annotations

import copy
import json
import math
import os
import sys

import numpy as np
from PIL import Image

RUN = r"C:\Users\赵紫阳\.codex\visualizations\2026\09\20\01a0bcff-6673-7410-b0a9-ad1c84270d1d\wx78"
sys.path.insert(0, os.path.join(RUN, "official"))
import kanim  # noqa: E402
import render_anim as ra  # noqa: E402

DS = r"E:\SteamLibrary\steamapps\common\dont_starve\data\anim"
EMOTE_MOD = r"E:\SteamLibrary\steamapps\common\dont_starve\mods\workshop-2649864463\anim\player_emotes.zip"
OUT = os.path.join(RUN, "final")
QA = os.path.join(RUN, "qa")

CELL_W, CELL_H = 192, 208
COLS, ROWS = 8, 11
RENDER_SCALE = 3.0
MARGIN = 10
PAD = 2

WX78 = os.path.join(DS, "wx78.zip")
BUILD = kanim.load_build_from_zip(WX78)
ATLAS = ra.load_atlas(WX78)

HEAD_PARTS = {"headbase", "headbase_hat", "face", "cheeks", "lens_eye", "SWAP_FACE"}
FACE_LEAD_ELEMENTS = {"face", "lens_eye"}

ROW_SPECS = [
    ("idle", 6, ("ds", "player_idles.zip", "idle_loop", 8), None),
    ("running-right", 8, ("ds", "player_basic.zip", "run_loop", 5), None),
    ("running-left", 8, ("ds", "player_basic.zip", "run_loop", 5), None),
    ("waving", 4, ("mod", "player_emotes.zip", "emote_waving", None), [0, 14, 29, 44]),
    # The client forces this row on pointer-enter.  WX-78 has no character-specific
    # idle in the single-player install, so the hover row carries the official
    # hot-weather idle: a calm, size-consistent loop.
    ("jumping", 5, ("ds", "player_idles.zip", "idle_hot_loop", 8), None),
    ("failed", 8, ("ds", "player_idles.zip", "idle_sanity_loop", 8), None),
    ("waiting", 6, ("ds", "player_idles.zip", "idle_inaction", 8), None),
    ("running", 6, ("ds", "player_actions_item.zip", "build_loop", 8), None),
    ("review", 6, ("ds", "player_actions.zip", "dial_loop", None), None),
]

LOOK_A = [0, 22.5, 45, 67.5, 90, 112.5, 135, 157.5]
LOOK_B = [180, 202.5, 225, 247.5, 270, 292.5, 315, 337.5]

LOOK_ROTATION_DEG = 16.0
LOOK_HEAD_LEAD = 2.0
LOOK_HEAD_LEAD_Y = 7.5
LOOK_FACE_LEAD = 12.0
LOOK_FACE_LEAD_Y = 15.0
LOOK_PIVOT_OFFSET = 55.0


def pick_anim(tag, zip_name, anim_name, facing):
    if tag == "mod":
        path = EMOTE_MOD
    else:
        path = os.path.join(DS, zip_name)
    anims, _t, _v = kanim.load_anim_from_zip(path)
    matches = [a for a in anims if a.name == anim_name]
    if not matches:
        raise KeyError(f"{anim_name} not in {zip_name}")
    if facing is not None:
        exact = [a for a in matches if a.facing == facing]
        if exact:
            return exact[0]
    return matches[0]


def sample_indices(nframes, wanted):
    if wanted >= nframes:
        return list(range(nframes))
    usable = max(1, nframes - 1)
    idx = [int(round(i * usable / wanted)) % nframes for i in range(wanted)]
    seen, uniq = set(), []
    for i in idx:
        if i not in seen:
            seen.add(i)
            uniq.append(i)
    return uniq


def content_box(img, origin):
    if img is None:
        return origin[0], origin[1], origin[0] + 1e-3, origin[1] + 1e-3
    a = img[:, :, 3] > 0.5
    ys, xs = np.nonzero(a)
    if len(xs) == 0:
        return origin[0], origin[1], origin[0] + 1, origin[1] + 1
    x0 = origin[0] + (xs.min() - PAD) / RENDER_SCALE
    y0 = origin[1] + (ys.min() - PAD) / RENDER_SCALE
    x1 = origin[0] + (xs.max() + 1 - PAD) / RENDER_SCALE
    y1 = origin[1] + (ys.max() + 1 - PAD) / RENDER_SCALE
    return x0, y0, x1, y1


def place_row(rendered):
    boxes = [content_box(img, origin) for img, origin in rendered]
    ux0 = min(b[0] for b in boxes)
    uy0 = min(b[1] for b in boxes)
    ux1 = max(b[2] for b in boxes)
    uy1 = max(b[3] for b in boxes)
    return place_with(rendered, (ux0, uy0, ux1, uy1))


def place_with(rendered, box):
    ux0, uy0, ux1, uy1 = box
    bw, bh = max(1e-6, ux1 - ux0), max(1e-6, uy1 - uy0)
    s = min((CELL_W - 2 * MARGIN) / bw, (CELL_H - 2 * MARGIN) / bh)
    dx = MARGIN + (CELL_W - 2 * MARGIN - bw * s) / 2.0
    dy = MARGIN + (CELL_H - 2 * MARGIN - bh * s)
    cells = []
    for img, (ox, oy) in rendered:
        px = dx + ((ox - PAD / RENDER_SCALE) - ux0) * s
        py = dy + ((oy - PAD / RENDER_SCALE) - uy0) * s
        k = s / RENDER_SCALE
        w = max(1, int(round(img.shape[1] * k)))
        h = max(1, int(round(img.shape[0] * k)))
        tile = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8), "RGBA").resize((w, h), Image.LANCZOS)
        cell = Image.new("RGBA", (CELL_W, CELL_H), (0, 0, 0, 0))
        cell.alpha_composite(tile, (int(round(px)), int(round(py))))
        cells.append(cell)
    return cells, {"scale": s, "box": [ux0, uy0, ux1, uy1]}


def apply_look(frame, direction_deg):
    fr = copy.deepcopy(frame)
    ang = math.radians(direction_deg)
    dx = math.sin(ang)
    dy = -math.cos(ang)
    pivot = None
    for el in fr.elements:
        if el.name == "headbase":
            pivot = (el.m[4], el.m[5] + LOOK_PIVOT_OFFSET)
            break
    if pivot is None:
        return fr
    rot = math.radians(LOOK_ROTATION_DEG) * dx
    ca, sa = math.cos(rot), math.sin(rot)
    px, py = pivot
    for el in fr.elements:
        if el.name in HEAD_PARTS or el.layername in HEAD_PARTS:
            a, b, c, d, tx, ty = el.m
            na = a * ca - b * sa
            nb = a * sa + b * ca
            nc = c * ca - d * sa
            nd = c * sa + d * ca
            vx, vy = tx - px, ty - py
            nx = px + vx * ca - vy * sa + dx * LOOK_HEAD_LEAD
            ny = py + vx * sa + vy * ca + dy * LOOK_HEAD_LEAD * LOOK_HEAD_LEAD_Y
            if el.name in FACE_LEAD_ELEMENTS:
                nx += dx * LOOK_FACE_LEAD
                ny += dy * LOOK_FACE_LEAD_Y
            el.m = (na, nb, nc, nd, nx, ny)
    return fr


def look_probe() -> None:
    idle = pick_anim("ds", "player_idles.zip", "idle_loop", 8)
    base_frame = idle.frames[0]
    base_img, base_origin = ra.render_frame_from(BUILD, base_frame, ATLAS, scale=1.6)
    dirs = [0, 45, 90, 135, 180, 225, 270, 315]
    tiles = [Image.fromarray(np.clip(base_img, 0, 255).astype(np.uint8), "RGBA")]
    for deg in dirs:
        fr = apply_look(base_frame, deg)
        img, _origin = ra.render_frame_from(BUILD, fr, ATLAS, scale=1.6)
        tiles.append(Image.fromarray(np.clip(img, 0, 255).astype(np.uint8), "RGBA"))
    w = max(t.width for t in tiles) + 8
    h = max(t.height for t in tiles) + 8
    sheet = Image.new("RGB", (len(tiles) * w, h), (255, 0, 255))
    for i, t in enumerate(tiles):
        sheet.paste(t, (i * w + 4, 4), t)
    path = os.path.join(QA, "look-probe.png")
    sheet.save(path)
    print(path)


def main() -> None:
    if "--look-probe" in sys.argv:
        os.makedirs(QA, exist_ok=True)
        look_probe()
        return
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(QA, exist_ok=True)
    rows = []
    provenance = {}

    for row, (name, wanted, spec, explicit) in enumerate(ROW_SPECS):
        tag, zip_name, anim_name, facing = spec
        anim = pick_anim(tag, zip_name, anim_name, facing)
        if explicit is not None:
            idx = list(explicit)
        else:
            idx = sample_indices(len(anim.frames), wanted)
        rendered = []
        for fi in idx:
            img, origin = ra.render_frame_from(BUILD, anim.frames[fi], ATLAS, scale=RENDER_SCALE)
            rendered.append((img, origin))
        cells, meta = place_row(rendered)
        if name == "running-left":
            cells = [c.transpose(Image.FLIP_LEFT_RIGHT) for c in cells]
        if name == "idle":
            cells = cells + [cells[0].copy()]
        rows.append((name, len(idx), cells, meta))
        provenance[name] = {
            "source": f"{tag}/{zip_name}/{anim_name}",
            "facing": anim.facing,
            "frame_indices": idx,
            "frame_selection": (
                "explicit official frames" if explicit is not None
                else "even sample of the clip"
            ),
            "source_frame_count": len(anim.frames),
            "fps": anim.frame_rate,
            "scale": round(meta["scale"], 4),
        }
        print(f"row {row} {name:14s} <- {tag}/{anim_name} frames {idx} scale {meta['scale']:.3f}")

    tag, zip_name, anim_name, facing = ROW_SPECS[0][2]
    idle = pick_anim(tag, zip_name, anim_name, facing)
    base_frame = idle.frames[0]
    base_img, base_origin = ra.render_frame_from(BUILD, base_frame, ATLAS, scale=RENDER_SCALE)
    base_cells, base_meta = place_row([(base_img, base_origin)])

    for row_name, angles in (("look-directions-a", LOOK_A), ("look-directions-b", LOOK_B)):
        rendered = []
        for deg in angles:
            fr = apply_look(base_frame, deg)
            img, origin = ra.render_frame_from(BUILD, fr, ATLAS, scale=RENDER_SCALE)
            rendered.append((img, origin))
        cells, lmeta = place_with(rendered, tuple(base_meta["box"]))
        rows.append((row_name, len(angles), cells, lmeta))
        provenance[row_name] = {
            "source": f"{tag}/{zip_name}/{anim_name} frame 0 + official head rotation",
            "angles": angles,
            "registration": "neutral frame registration (row 0 column 6)",
            "mechanics": (
                "official front head group rotated up to "
                f"{LOOK_ROTATION_DEG:.0f} deg about the neck, face/eye sprites led by up to "
                f"{LOOK_FACE_LEAD:.0f} units; torso/arms stay in the official idle pose"
            ),
            "scale": round(lmeta["scale"], 4),
        }
        print(f"row {len(rows)-1} {row_name} <- official head composition, {len(angles)} directions")

    def compose(nrows, path_png, path_webp):
        atlas = Image.new("RGBA", (COLS * CELL_W, nrows * CELL_H), (0, 0, 0, 0))
        for r, (name, used, cells, _meta) in enumerate(rows[:nrows]):
            for c, cell in enumerate(cells[:COLS]):
                atlas.alpha_composite(cell, (c * CELL_W, r * CELL_H))
        atlas.save(path_png)
        atlas.save(path_webp, format="WEBP", lossless=True, quality=100, method=6)
        return atlas

    compose(9, os.path.join(OUT, "spritesheet.png"), os.path.join(OUT, "spritesheet.webp"))
    final = compose(11, os.path.join(OUT, "spritesheet-extended.png"),
                    os.path.join(OUT, "spritesheet-extended.webp"))
    provenance["_notes"] = {
        "hidden_layers": sorted(ra.HIDDEN_LAYERS),
        "hidden_element_names": sorted(ra.HIDDEN_ELEMENT_NAMES),
        "hidden_layer_reason": (
            "equipment-only layers (carry arm, hat-shaped head) that Klei hides "
            "for the default unequipped look"
        ),
        "row_1_2_facing": (
            "the official side view faces screen-right, so row 1 running-right is "
            "the unmirrored render and row 2 running-left is its horizontal mirror"
        ),
        "row_4_note": (
            "the client forces the jumping row on pointer-enter (hover); WX-78 has "
            "no single-player character-specific idle, so the row carries the "
            "official hot-weather idle (idle_hot_loop): a calm, size-consistent loop"
        ),
    }
    with open(os.path.join(OUT, "provenance.json"), "w", encoding="utf-8") as fh:
        json.dump(provenance, fh, indent=2, ensure_ascii=False)
    print("final atlas", final.size)


if __name__ == "__main__":
    main()
