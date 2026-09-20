"""Assemble the Codex v2 pet atlas (8x11, 192x208 cells) from official
Don't Starve animation frames, plus a 16-pose look loop built from the official
head parts."""

from __future__ import annotations

import copy
import json
import math
import os
import sys

import numpy as np
from PIL import Image

RUN = r"C:\Users\赵紫阳\.codex\visualizations\2026\09\14\01a0a048-aa99-7151-906a-1714b42c5616\wilson"
sys.path.insert(0, os.path.join(RUN, "official"))
import kanim  # noqa: E402
import render_anim as ra  # noqa: E402

DS = r"E:\SteamLibrary\steamapps\common\dont_starve\data\anim"
DST = r"E:\SteamLibrary\steamapps\common\Don't Starve Together\data\anim"
OUT = os.path.join(RUN, "final")
QA = os.path.join(RUN, "qa")

CELL_W, CELL_H = 192, 208
COLS, ROWS = 8, 11
RENDER_SCALE = 3.0
MARGIN = 10
PAD = 2  # render_frame margin, in canvas pixels

HEAD_PARTS = {"headbase", "headbase_hat", "face", "cheeks", "hair", "hair_hat",
              "HAIR_HAT", "HEAD_HAT", "lens_eye", "SWAP_FACE", "BEARD", "hairfront"}

# (name, frames, (source tag, zip, animation, facing), explicit frame indices)
ROW_SPECS = [
    ("idle", 6, ("ds", "player_idles.zip", "idle_loop", 8), None),
    ("running-right", 8, ("ds", "player_basic.zip", "run_loop", 5), None),
    ("running-left", 8, ("ds", "player_basic.zip", "run_loop", 5), None),
    ("waving", 4, ("dst", "player_emotes.zip", "emote_waving", None), None),
    # The client forces this row on pointer-enter.  Hovering should read as a
    # calm reaction, so it carries Wilson's own idle (_wilson) rather than the
    # jump; the crafting motion stays on the working row (row 7).
    ("jumping", 5, ("dst", "player_idles_wilson.zip", "idle_wilson", 8), [0, 15, 30, 45, 60]),
    ("failed", 8, ("ds", "player_idles.zip", "idle_sanity_loop", 8), None),
    ("waiting", 6, ("ds", "player_idles.zip", "idle_inaction", 8), None),
    ("running", 6, ("ds", "player_actions_item.zip", "build_loop", 8), None),
    ("review", 6, ("ds", "player_actions.zip", "dial_loop", None), None),
]

LOOK_A = [0, 22.5, 45, 67.5, 90, 112.5, 135, 157.5]
LOOK_B = [180, 202.5, 225, 247.5, 270, 292.5, 315, 337.5]


def load_all():
    out = {}
    for tag, root in (("ds", DS), ("dst", DST)):
        wilson = os.path.join(root, "wilson.zip")
        out[tag] = (kanim.load_build_from_zip(wilson), ra.load_atlas(wilson))
    return out


def pick_anim(tag, zip_name, anim_name, facing):
    root = DS if tag == "ds" else DST
    anims, _t, _v = kanim.load_anim_from_zip(os.path.join(root, zip_name))
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


def sample_indices_normal_height(build, atlas, anim, wanted):
    """Pick frames whose sprite height is close to the animation's median, so a
    squash-and-stretch clip (the jump) keeps a consistent pet size."""
    boxes = []
    for fr in anim.frames:
        img, origin = ra.render_frame_from(build, fr, atlas, scale=RENDER_SCALE)
        boxes.append(content_box(img, origin))
    heights = np.array([b[3] - b[1] for b in boxes])
    median = float(np.median(heights))
    for tol in (0.05, 0.08, 0.12):
        ok = [i for i, h in enumerate(heights) if median * (1 - tol) <= h <= median * (1 + tol)]
        if len(ok) >= wanted:
            break
    if len(ok) < wanted:
        ok = [i for i, h in enumerate(heights) if h > 0.01]
    if len(ok) < wanted:
        ok = list(range(len(anim.frames)))
    picks = [ok[int(round(i * (len(ok) - 1) / (wanted - 1)))] for i in range(wanted)]
    return sorted(set(picks))


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
    """rendered: list of (img, origin). Returns list of 192x208 RGBA images."""
    boxes = [content_box(img, origin) for img, origin in rendered]
    ux0 = min(b[0] for b in boxes)
    uy0 = min(b[1] for b in boxes)
    ux1 = max(b[2] for b in boxes)
    uy1 = max(b[3] for b in boxes)
    return place_with(rendered, (ux0, uy0, ux1, uy1))


def place_with(rendered, box):
    """Place frames using an explicit build-space box (shared registration)."""
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


# Look-direction amplitudes: the official idle art is a single front pose, so a
# look direction is the official head group turned about the neck plus the
# official face sprite (eyes, brows, eye bags) led toward the gaze.  The values
# are tuned so the four cardinals stay unmistakable at the 192x208 pet size
# without pushing the eyes off the face.
LOOK_ROTATION_DEG = 16.0
LOOK_HEAD_LEAD = 2.0
# the whole head lifts/sinks for the up/down cardinals (the face alone was too
# subtle to read once the sprite is scaled into a 192x208 cell)
LOOK_HEAD_LEAD_Y = 7.5
LOOK_FACE_LEAD = 12.0
LOOK_FACE_LEAD_Y = 15.0


def apply_look(frame, direction_deg):
    """Turn the official head group toward a screen-space direction.

    0 deg = up, 90 = screen-right, 180 = down, 270 = screen-left.
    """
    fr = copy.deepcopy(frame)
    ang = math.radians(direction_deg)
    dx = math.sin(ang)
    dy = -math.cos(ang)
    pivot = None
    for el in fr.elements:
        if el.name == "headbase":
            pivot = (el.m[4], el.m[5] + 55.0)
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
            if el.name == "face":
                # the face sprite carries the eyes, so leading it is what makes
                # the up/down cardinals read at pet size
                nx += dx * LOOK_FACE_LEAD
                ny += dy * LOOK_FACE_LEAD_Y
            el.m = (na, nb, nc, nd, nx, ny)
    return fr


def main():
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(QA, exist_ok=True)
    builds = load_all()
    rows = []          # list of (name, cols, [cells], meta)
    provenance = {}

    for row, (name, wanted, spec, explicit) in enumerate(ROW_SPECS):
        tag, zip_name, anim_name, facing = spec
        build, atlas = builds[tag]
        anim = pick_anim(tag, zip_name, anim_name, facing)
        if explicit is not None:
            idx = list(explicit)
        elif name == "jumping":
            idx = sample_indices_normal_height(build, atlas, anim, wanted)
        else:
            idx = sample_indices(len(anim.frames), wanted)
        rendered = []
        for fi in idx:
            img, origin = ra.render_frame_from(build, anim.frames[fi], atlas, scale=RENDER_SCALE)
            rendered.append((img, origin))
        cells, meta = place_row(rendered)
        if name == "running-left":
            # the official side view already faces screen-right, so the leftward
            # row is its horizontal mirror (the client plays row 1 for a
            # rightward drag and row 2 for a leftward drag)
            cells = [c.transpose(Image.FLIP_LEFT_RIGHT) for c in cells]
        if name == "idle":
            # the v2 contract reserves (row 0, column 6) for the neutral
            # front-facing frame used as the look-direction reference
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

    # ---- look rows: official front pose + official head/face parts ----------
    tag, zip_name, anim_name, facing = ROW_SPECS[0][2]
    build, atlas = builds[tag]
    idle = pick_anim(tag, zip_name, anim_name, facing)
    base_frame = idle.frames[0]
    base_img, base_origin = ra.render_frame_from(build, base_frame, atlas, scale=RENDER_SCALE)
    base_cells, base_meta = place_row([(base_img, base_origin)])

    for row_name, angles in (("look-directions-a", LOOK_A), ("look-directions-b", LOOK_B)):
        rendered = []
        for deg in angles:
            fr = apply_look(base_frame, deg)
            img, origin = ra.render_frame_from(build, fr, atlas, scale=RENDER_SCALE)
            rendered.append((img, origin))
        # every look cell uses the *neutral frame's* registration so the 16
        # directions share one scale and baseline with the idle row
        cells, lmeta = place_with(rendered, tuple(base_meta["box"]))
        rows.append((row_name, len(angles), cells, lmeta))
        provenance[row_name] = {
            "source": f"{tag}/{zip_name}/{anim_name} frame 0 + official head rotation",
            "angles": angles,
            "registration": "neutral frame registration (row 0 column 6)",
            "mechanics": (
                "official front head group rotated up to "
                f"{LOOK_ROTATION_DEG:.0f} deg about the neck, face sprite led by up to "
                f"{LOOK_FACE_LEAD:.0f} units; torso/arms stay in the official idle pose"
            ),
            "scale": round(lmeta["scale"], 4),
        }
        print(f"row {len(rows)-1} {row_name} <- official head composition, {len(angles)} directions")

    # ---- write the 8x9 intermediate and the 8x11 final atlas ---------------
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
            "equipment-only layers (carry arm, hat-shaped head) that Klei hides for "
            "a bare-handed, hatless Wilson; drawing them added a third arm"
        ),
        "row_1_2_facing": (
            "the official side view faces screen-right, so row 1 running-right is the "
            "unmirrored render and row 2 running-left is its horizontal mirror; the "
            "client plays row 1 for a rightward drag and row 2 for a leftward drag"
        ),
        "row_4_note": (
            "the client forces the jumping row on pointer-enter (hover); the row now "
            "carries Wilson's own calm idle (_wilson) instead of the jump"
        ),
    }
    with open(os.path.join(OUT, "provenance.json"), "w", encoding="utf-8") as fh:
        json.dump(provenance, fh, indent=2, ensure_ascii=False)
    print("final atlas", final.size)


if __name__ == "__main__":
    main()
