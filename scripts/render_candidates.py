"""Render every candidate official animation to review contact sheets."""

from __future__ import annotations

import json
import os
import sys

from PIL import Image, ImageDraw

RUN = r"C:\Users\赵紫阳\.codex\visualizations\2026\09\14\01a0a048-aa99-7151-906a-1714b42c5616\wilson"
sys.path.insert(0, os.path.join(RUN, "official"))
import kanim  # noqa: E402
import render_anim as ra  # noqa: E402

DS = r"E:\SteamLibrary\steamapps\common\dont_starve\data\anim"
DST = r"E:\SteamLibrary\steamapps\common\Don't Starve Together\data\anim"
OUT = os.path.join(RUN, "official", "anim_ref")

CANDIDATES = [
    ("ds", "player_idles.zip", "idle_loop"),
    ("ds", "player_basic.zip", "run_pre"),
    ("ds", "player_basic.zip", "run_loop"),
    ("ds", "player_basic.zip", "run_pst"),
    ("ds", "player_jump.zip", "jump"),
    ("ds", "player_idles.zip", "idle_sanity_pre"),
    ("ds", "player_idles.zip", "idle_sanity_loop"),
    ("ds", "player_idles.zip", "idle_inaction"),
    ("ds", "player_idles.zip", "idle_inaction_sanity"),
    ("ds", "player_actions_item.zip", "build_pre"),
    ("ds", "player_actions_item.zip", "build_loop"),
    ("ds", "player_actions_item.zip", "build_pst"),
    ("ds", "player_actions.zip", "dial_loop"),
    ("ds", "player_actions.zip", "distress_loop"),
    ("ds", "player_actions_eat.zip", "hungry"),
    ("ds", "player_mime.zip", "mime1"),
    ("ds", "player_idles.zip", "idle_shiver_pre"),
    ("dst", "player_idles_wilson.zip", "idle_wilson"),
    ("dst", "player_idles_wilson.zip", "idle_wilson_beard"),
    ("dst", "player_emotes.zip", "emote_waving"),
    ("dst", "player_actions.zip", "research"),
]


def build_and_atlas(tag):
    root = DS if tag == "ds" else DST
    wilson = os.path.join(root, "wilson.zip")
    return kanim.load_build_from_zip(wilson), ra.load_atlas(wilson)


def render_one(tag, zip_name, anim_name, scale=1.6, facing=None):
    root = DS if tag == "ds" else DST
    path = os.path.join(root, zip_name)
    if not os.path.exists(path):
        return None
    build, atlas = build_and_atlas(tag)
    anims, _table, _ver = kanim.load_anim_from_zip(path)
    matches = [a for a in anims if a.name == anim_name]
    if not matches:
        return None
    if facing is not None:
        sel = [a for a in matches if a.facing == facing]
        anim = sel[0] if sel else matches[0]
    else:
        anim = matches[0]
    imgs, meta = ra.render_animation(build, anim, atlas, scale=scale, vflip=True)
    if not imgs:
        return None
    return anim, imgs, meta, len(matches)


def sheet(anim, imgs, meta, cols=8, label_prefix=""):
    cw, ch = meta[2], meta[3]
    rows = (len(imgs) + cols - 1) // cols
    img = Image.new("RGB", (cols * (cw + 4), rows * (ch + 4)), (255, 0, 255))
    d = ImageDraw.Draw(img)
    for i, im in enumerate(imgs):
        t = ra.to_pil(im)
        x, y = (i % cols) * (cw + 4), (i // cols) * (ch + 4)
        img.paste(t, (x, y), t)
        d.rectangle([x, y, x + 34, y + 14], fill=(0, 0, 0))
        d.text((x + 2, y + 2), f"{label_prefix}{i}", fill=(255, 255, 0))
    return img


def main():
    os.makedirs(OUT, exist_ok=True)
    report = []
    for tag, zip_name, anim_name in CANDIDATES:
        res = render_one(tag, zip_name, anim_name)
        if res is None:
            print(f"SKIP {tag} {zip_name} {anim_name}")
            report.append({"tag": tag, "zip": zip_name, "anim": anim_name, "status": "missing"})
            continue
        anim, imgs, meta, variants = res
        out = os.path.join(OUT, f"{tag}_{zip_name.replace('.zip','')}_{anim_name}.png")
        sheet(anim, imgs, meta).save(out)
        print(f"{tag} {anim_name:22s} frames={len(imgs):3d} facing={anim.facing} variants={variants} -> {os.path.basename(out)}")
        report.append({"tag": tag, "zip": zip_name, "anim": anim_name, "status": "ok",
                       "frames": len(imgs), "facing": anim.facing, "variants": variants,
                       "fps": anim.frame_rate, "sheet": os.path.basename(out)})
    with open(os.path.join(OUT, "candidates.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)


if __name__ == "__main__":
    main()
