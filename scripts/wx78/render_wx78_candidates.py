"""Render candidate WX-78 animations with WX-78's own build/atlas."""

from __future__ import annotations

import json
import os
import sys

from PIL import Image, ImageDraw

RUN = r"C:\Users\赵紫阳\.codex\visualizations\2026\09\20\01a0bcff-6673-7410-b0a9-ad1c84270d1d\wx78"
sys.path.insert(0, os.path.join(RUN, "official"))
import kanim  # noqa: E402
import render_anim as ra  # noqa: E402

DS = r"E:\SteamLibrary\steamapps\common\dont_starve"
ANIM = os.path.join(DS, "data", "anim")
EMOTE_MOD = r"E:\SteamLibrary\steamapps\common\dont_starve\mods\workshop-2649864463\anim\player_emotes.zip"
OUT = os.path.join(RUN, "official", "anim_ref")

WX78 = os.path.join(ANIM, "wx78.zip")
BUILD = kanim.load_build_from_zip(WX78)
ATLAS = ra.load_atlas(WX78)

CANDIDATES = [
    ("ds", "player_idles.zip", "idle_loop"),
    ("ds", "player_idles.zip", "idle_hot_loop"),
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
    ("mod", "player_emotes.zip", "emote_waving"),
]


def zip_path_for(tag: str, zip_name: str) -> str:
    return EMOTE_MOD if tag == "mod" else os.path.join(ANIM, zip_name)


def render_one(tag, zip_name, anim_name, scale=1.6):
    path = zip_path_for(tag, zip_name)
    if not os.path.exists(path):
        return None
    anims, _table, _ver = kanim.load_anim_from_zip(path)
    matches = [a for a in anims if a.name == anim_name]
    if not matches:
        return []
    results = []
    seen_facings = set()
    for anim in matches:
        if anim.facing in seen_facings:
            continue
        seen_facings.add(anim.facing)
        imgs, meta = ra.render_animation(BUILD, anim, ATLAS, scale=scale, vflip=True)
        if imgs:
            results.append((anim, imgs, meta))
    return results


def sheet(anim, imgs, meta, cols=8):
    cw, ch = meta[2], meta[3]
    rows = (len(imgs) + cols - 1) // cols
    img = Image.new("RGB", (cols * (cw + 4), rows * (ch + 4)), (255, 0, 255))
    d = ImageDraw.Draw(img)
    for i, im in enumerate(imgs):
        t = ra.to_pil(im)
        x, y = (i % cols) * (cw + 4), (i // cols) * (ch + 4)
        img.paste(t, (x, y), t)
        d.rectangle([x, y, x + 34, y + 14], fill=(0, 0, 0))
        d.text((x + 2, y + 2), str(i), fill=(255, 255, 0))
    return img


def main() -> None:
    os.makedirs(OUT, exist_ok=True)
    report = []
    for tag, zip_name, anim_name in CANDIDATES:
        results = render_one(tag, zip_name, anim_name)
        if not results:
            print(f"SKIP {tag} {zip_name} {anim_name}")
            report.append({"tag": tag, "zip": zip_name, "anim": anim_name, "status": "missing"})
            continue
        for anim, imgs, meta in results:
            suffix = f"_f{anim.facing}" if len(results) > 1 else ""
            out = os.path.join(OUT, f"{tag}_{zip_name.replace('.zip', '')}_{anim_name}{suffix}.png")
            sheet(anim, imgs, meta).save(out)
            print(f"{tag} {anim_name:20s} facing={anim.facing} frames={len(imgs):3d} "
                  f"fps={anim.frame_rate} -> {os.path.basename(out)}")
            report.append({"tag": tag, "zip": zip_name, "anim": anim_name,
                           "status": "ok", "frames": len(imgs), "facing": anim.facing,
                           "fps": anim.frame_rate, "sheet": os.path.basename(out)})
    with open(os.path.join(OUT, "candidates.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)


if __name__ == "__main__":
    main()
