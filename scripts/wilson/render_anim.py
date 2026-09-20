"""Render Klei (Don't Starve) animations from build.bin + anim.bin + the atlas.

Each animation frame is a list of elements; every element is a quad taken from
the atlas (given by the build symbol frame's UV triangles) placed by an affine
matrix.  Rendering therefore reduces to: for each element, solve the affine map
from canvas pixels to atlas pixels and resample the atlas once.
"""

from __future__ import annotations

import os
import sys

import numpy as np
from PIL import Image, ImageDraw

RUN = r"C:\Users\赵紫阳\.codex\visualizations\2026\09\14\01a0a048-aa99-7151-906a-1714b42c5616\wilson"
sys.path.insert(0, os.path.join(RUN, "official"))
import ktex  # noqa: E402
import kanim  # noqa: E402

# Layers Klei only shows when something is equipped.  A bare-handed, hatless
# Wilson must not draw them, otherwise the carry arm and the hat-shaped head
# appear on top of the default look (the game hides these via AnimState).
HIDDEN_LAYERS = {
    "ARM_carry",      # arm holding a carried object
    "HEAD_HAT",       # head shaded for a worn hat
    "HAIR_HAT",
    "HAT",
    "hair_hat",
    "SWAP_BODY",
    "SWAP_FACE",
    "BEARD",
    "LANTERN_OVERLAY",
}

HIDDEN_ELEMENT_NAMES = {
    "headbase_hat",
    "swap_hat",
    "swap_object",
    "swap_lantern",
    "swap_goo",
    "LANTERN_OVERLAY",
}


def is_visible_element(el) -> bool:
    """True when the element belongs to Wilson's default, unequipped look."""
    if el.layername in HIDDEN_LAYERS or el.name in HIDDEN_ELEMENT_NAMES:
        return False
    if el.layername in HIDDEN_ELEMENT_NAMES:
        return False
    return True


def solve_affine(src, dst):
    """Least-squares 2x3 affine mapping src -> dst (both lists of (x, y))."""
    a = np.asarray(src, dtype=np.float64)
    b = np.asarray(dst, dtype=np.float64)
    A = np.hstack([a, np.ones((len(a), 1))])
    sol, *_ = np.linalg.lstsq(A, b, rcond=None)
    return sol.T  # 2x3 : [[m00, m01, m02], [m10, m11, m12]]


def invert_affine(m):
    det = m[0, 0] * m[1, 1] - m[0, 1] * m[1, 0]
    if abs(det) < 1e-12:
        return None
    inv = np.array(
        [
            [m[1, 1] / det, -m[0, 1] / det],
            [-m[1, 0] / det, m[0, 0] / det],
        ]
    )
    t = np.array([m[0, 2], m[1, 2]])
    return np.hstack([inv, (-inv @ t).reshape(2, 1)])


def element_affines(element, sym_frame, atlas_w, atlas_h, vflip=True):
    """Return (matrix local->atlas px, matrix local->canvas px, quad corners)."""
    local, uv = sym_frame.corners()
    if not local:
        return None
    a, b, c, d, tx, ty = element.m
    M = np.array([[a, c, tx], [b, d, ty]], dtype=np.float64)
    local_np = np.asarray(local, dtype=np.float64)
    world = (M[:, :2] @ local_np.T).T + M[:, 2]
    if vflip:
        uv_px = [(u * atlas_w, (1.0 - v) * atlas_h) for (u, v) in uv]
    else:
        uv_px = [(u * atlas_w, v * atlas_h) for (u, v) in uv]
    F = solve_affine(world, uv_px)      # canvas(world) -> atlas px
    return F, M, world


def sample_bilinear(atlas, xs, ys):
    """Sample an (H, W, 4) uint8 array at float coords; returns (…, 4) float."""
    h, w = atlas.shape[:2]
    xs = np.clip(xs, 0, w - 1.001)
    ys = np.clip(ys, 0, h - 1.001)
    x0 = np.floor(xs).astype(np.int32)
    y0 = np.floor(ys).astype(np.int32)
    fx = (xs - x0)[..., None]
    fy = (ys - y0)[..., None]
    c00 = atlas[y0, x0].astype(np.float32)
    c10 = atlas[y0, x0 + 1].astype(np.float32)
    c01 = atlas[y0 + 1, x0].astype(np.float32)
    c11 = atlas[y0 + 1, x0 + 1].astype(np.float32)
    return (c00 * (1 - fx) * (1 - fy) + c10 * fx * (1 - fy)
            + c01 * (1 - fx) * fy + c11 * fx * fy)


def triangle_mask(world, minx, miny, scale, pad, box, supersample=4):
    """Anti-aliased coverage mask for one element's two triangles.

    Klei draws every element as two textured triangles.  Sampling the element's
    whole axis-aligned bounding box instead would also read atlas texels that
    belong to neighbouring sprites, so rotated or sheared elements drag foreign
    fragments into the frame.  Limiting the sampling to the element's own
    triangles is what keeps every drawn pixel inside the element's atlas rect.
    """
    ex0, ey0, ex1, ey1 = box
    bw, bh = ex1 - ex0, ey1 - ey0
    if bw <= 0 or bh <= 0:
        return None
    mask = Image.new("L", (bw * supersample, bh * supersample), 0)
    draw = ImageDraw.Draw(mask)
    for start in range(0, len(world) - 2, 3):
        points = []
        for i in range(3):
            wx, wy = world[start + i]
            cx = (wx - minx) * scale + pad - ex0
            cy = (wy - miny) * scale + pad - ey0
            points.append((cx * supersample, cy * supersample))
        draw.polygon(points, fill=255)
    mask = mask.resize((bw, bh), Image.BOX)
    return np.asarray(mask, dtype=np.float32) / 255.0


def render_frame(build, anim, frame_index, atlas, scale=1.0, vflip=True,
                 alpha_cut=0.0):
    """Render one animation frame to an RGBA float array (canvas space)."""
    frame = anim.frames[frame_index % len(anim.frames)]
    return render_frame_from(build, frame, atlas, scale=scale, vflip=vflip,
                             alpha_cut=alpha_cut)


def render_frame_from(build, frame, atlas, scale=1.0, vflip=True, alpha_cut=0.0):
    """Render an explicit AnimFrame object (used by the look-direction builder)."""
    atlas_h, atlas_w = atlas.shape[:2]

    # Bounding box of every element in canvas space.
    plan = []
    minx = miny = np.inf
    maxx = maxy = -np.inf
    # Klei stores elements front-to-back, so the last one is drawn first.
    for el in reversed(frame.elements):
        if not is_visible_element(el):
            continue
        sym = build.symbols.get(el.hash)
        if sym is None or el.build_frame >= len(sym.frames):
            continue
        sym_frame = sym.frames[el.build_frame]
        info = element_affines(el, sym_frame, atlas_w, atlas_h, vflip)
        if info is None:
            continue
        F, M, world = info
        _local, uv = sym_frame.corners()
        if vflip:
            uv_px = [(u * atlas_w, (1.0 - v) * atlas_h) for (u, v) in uv]
        else:
            uv_px = [(u * atlas_w, v * atlas_h) for (u, v) in uv]
        plan.append((F, world, sym, el, uv_px))
        minx = min(minx, world[:, 0].min())
        maxx = max(maxx, world[:, 0].max())
        miny = min(miny, world[:, 1].min())
        maxy = max(maxy, world[:, 1].max())
    if not plan:
        return None, (0, 0)

    pad = 2
    w = int(np.ceil((maxx - minx) * scale)) + 2 * pad
    h = int(np.ceil((maxy - miny) * scale)) + 2 * pad
    canvas = np.zeros((h, w, 4), dtype=np.float32)

    ys, xs = np.mgrid[0:h, 0:w]
    world_x = (xs - pad) / scale + minx
    world_y = (ys - pad) / scale + miny

    for F, world, sym, el, uv_px in plan:
        # canvas pixel -> world -> atlas pixel
        pts = np.stack([world_x.ravel(), world_y.ravel()], axis=1)
        src = (F[:, :2] @ pts.T).T + F[:, 2]
        # keep bilinear reads inside this element's own atlas rectangle
        sx0 = min(p[0] for p in uv_px) + 0.5
        sx1 = max(p[0] for p in uv_px) - 0.5
        sy0 = min(p[1] for p in uv_px) + 0.5
        sy1 = max(p[1] for p in uv_px) - 0.5
        if sx1 < sx0:
            sx0 = sx1 = 0.5 * (sx0 + sx1)
        if sy1 < sy0:
            sy0 = sy1 = 0.5 * (sy0 + sy1)
        src[:, 0] = np.clip(src[:, 0], sx0, sx1)
        src[:, 1] = np.clip(src[:, 1], sy0, sy1)
        # limit work to the element's own bounding box
        ex0 = int(np.floor((world[:, 0].min() - minx) * scale)) + pad - 2
        ex1 = int(np.ceil((world[:, 0].max() - minx) * scale)) + pad + 2
        ey0 = int(np.floor((world[:, 1].min() - miny) * scale)) + pad - 2
        ey1 = int(np.ceil((world[:, 1].max() - miny) * scale)) + pad + 2
        ex0, ey0 = max(0, ex0), max(0, ey0)
        ex1, ey1 = min(w, ex1), min(h, ey1)
        if ex1 <= ex0 or ey1 <= ey0:
            continue
        mask = triangle_mask(world, minx, miny, scale, pad, (ex0, ey0, ex1, ey1))
        if mask is None:
            continue
        sx = src[:, 0].reshape(h, w)[ey0:ey1, ex0:ex1]
        sy = src[:, 1].reshape(h, w)[ey0:ey1, ex0:ex1]
        texel = sample_bilinear(atlas, sx, sy)
        a = texel[:, :, 3:4] / 255.0
        if alpha_cut > 0:
            a = np.where(a < alpha_cut, 0.0, a)
        a = a * mask[:, :, None]
        rgb = texel[:, :, :3]
        dst = canvas[ey0:ey1, ex0:ex1]
        dst_a = dst[:, :, 3:4] / 255.0
        out_a = a + dst_a * (1 - a)
        safe = np.where(out_a > 1e-6, out_a, 1.0)
        dst[:, :, :3] = (rgb * a + dst[:, :, :3] * dst_a * (1 - a)) / safe
        dst[:, :, 3:4] = out_a * 255.0

    return canvas, (minx, miny)


def render_animation(build, anim, atlas, scale=1.0, vflip=True):
    """Render every frame; returns (frames, offsets) with a shared origin."""
    pad = 2
    imgs, offs = [], []
    for i in range(len(anim.frames)):
        img, off = render_frame(build, anim, i, atlas, scale=scale, vflip=vflip)
        if img is None:
            continue
        imgs.append(img)
        offs.append(off)
    if not imgs:
        return [], (0, 0, 0, 0)

    # world-space box of every frame (each local canvas has a `pad` margin)
    boxes = []
    for img, (ox, oy) in zip(imgs, offs):
        w_world = (img.shape[1] - 2 * pad) / scale
        h_world = (img.shape[0] - 2 * pad) / scale
        boxes.append((ox, oy, ox + w_world, oy + h_world))
    gx = min(b[0] for b in boxes)
    gy = min(b[1] for b in boxes)
    gx1 = max(b[2] for b in boxes)
    gy1 = max(b[3] for b in boxes)
    width = int(np.ceil((gx1 - gx) * scale)) + 2 * pad
    height = int(np.ceil((gy1 - gy) * scale)) + 2 * pad

    out = []
    for img, (ox, oy) in zip(imgs, offs):
        canvas = np.zeros((height, width, 4), dtype=np.float32)
        dx = int(round((ox - gx) * scale))
        dy = int(round((oy - gy) * scale))
        h = min(img.shape[0], height - dy)
        w = min(img.shape[1], width - dx)
        canvas[dy : dy + h, dx : dx + w] = img[:h, :w]
        out.append(canvas)
    return out, (float(gx), float(gy), width, height)


def to_pil(canvas):
    return Image.fromarray(np.clip(canvas, 0, 255).astype(np.uint8), "RGBA")


def load_atlas(zip_path, atlas_name="atlas-0.tex"):
    import zipfile

    with zipfile.ZipFile(zip_path) as z:
        data = z.read(atlas_name)
    img = ktex.decode_mipmap(data, 0)
    return img[::-1, :]      # payloads are stored bottom-up
