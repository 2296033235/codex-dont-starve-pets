"""Calibrate which way a character's side-view animation faces.

Uses exact build geometry: the `face` sprite (eye screen / face plate) sits on
the front of the head, so comparing its translation against `headbase` tells us
which way the character is looking without any pixel heuristics.

Wilson's facing=5 is known to face screen-right (it ships as the pet's
running-right row), so he calibrates the sign.
"""

from __future__ import annotations

import os
import sys

RUN = r"C:\Users\赵紫阳\.codex\visualizations\2026\09\20\01a0bcff-6673-7410-b0a9-ad1c84270d1d\wx78"
sys.path.insert(0, os.path.join(RUN, "official"))
import kanim  # noqa: E402

DS = r"E:\SteamLibrary\steamapps\common\dont_starve\data\anim"
FACINGS = (5, 2)


def report(name: str, build_zip: str, anim_zip: str) -> None:
    build = kanim.load_build_from_zip(build_zip)
    want = {"face", "headbase", "lens_eye"}
    print(f"--- {name}")
    for facing in FACINGS:
        anims, _t, _v = kanim.load_anim_from_zip(anim_zip)
        matches = [a for a in anims if a.name == "run_loop" and a.facing == facing]
        if not matches:
            print(f"  facing={facing}: no run_loop")
            continue
        frame = matches[0].frames[0]
        found = {}
        for el in frame.elements:
            sym = build.symbols.get(el.hash)
            key = sym.name if sym else el.layername
            if key in want:
                found.setdefault(key, (el.m[4], el.m[5]))
        head = found.get("headbase")
        face = found.get("face")
        eye = found.get("lens_eye")
        detail = " ".join(f"{k}=({v[0]:.1f},{v[1]:.1f})" for k, v in sorted(found.items()))
        if head and face:
            delta = face[0] - head[0]
            side = "RIGHT" if delta > 0 else "LEFT"
            print(f"  facing={facing}: {detail} | face-head dx={delta:+.1f} -> {side}")
        else:
            print(f"  facing={facing}: {detail} | missing landmark")


def main() -> None:
    report("wilson (calibration: facing 5 is known screen-right)",
           os.path.join(DS, "wilson.zip"), os.path.join(DS, "player_basic.zip"))
    report("wx78", os.path.join(DS, "wx78.zip"), os.path.join(DS, "player_basic.zip"))


if __name__ == "__main__":
    main()
