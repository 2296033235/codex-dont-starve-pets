"""Pure-Python reader for Klei's BILD (build) and ANIM (animation) files.

The read order follows the GPL `krane` tool by "simplex"
(ktools/src/krane/kbuild_serialize.cpp and kanim_serialize.cpp).
Both formats end with a hash -> name table, so no hash function is required.
"""

from __future__ import annotations

import os
import struct
import zipfile
from dataclasses import dataclass, field


class Reader:
    def __init__(self, data: bytes):
        self.d = data
        self.o = 0

    def u32(self) -> int:
        v = struct.unpack_from("<I", self.d, self.o)[0]
        self.o += 4
        return v

    def i32(self) -> int:
        v = struct.unpack_from("<i", self.d, self.o)[0]
        self.o += 4
        return v

    def u8(self) -> int:
        v = self.d[self.o]
        self.o += 1
        return v

    def f32(self) -> float:
        v = struct.unpack_from("<f", self.d, self.o)[0]
        self.o += 4
        return v

    def string(self) -> str:
        n = self.u32()
        s = self.d[self.o : self.o + n].decode("utf-8", "replace")
        self.o += n
        return s

    def skip_string(self) -> None:
        self.o += self.u32()


# --------------------------------------------------------------------------- #
# build (BILD)
# --------------------------------------------------------------------------- #
@dataclass
class SymbolFrame:
    framenum: int
    duration: int
    bbox: tuple          # (x, y, w, h) in build units
    alphaidx: int
    alphacount: int
    verts: list = field(default_factory=list)   # [(x, y, z, u, v, w), ...] x3 per triangle

    def corners(self):
        """Return the quad corners (local x, y) and their (u, v) atlas coords."""
        local, uv = [], []
        for i in range(0, len(self.verts), 3):
            for j in range(3):
                x, y, _z, u, v, _w = self.verts[i + j]
                local.append((x, y))
                uv.append((u, v))
        return local, uv


@dataclass
class Symbol:
    hash: int
    name: str = ""
    frames: list = field(default_factory=list)


@dataclass
class Build:
    name: str
    atlases: list
    symbols: dict            # hash -> Symbol

    def by_name(self, name: str):
        for sym in self.symbols.values():
            if sym.name == name:
                return sym
        return None


def parse_build(data: bytes) -> Build:
    r = Reader(data)
    if data[0:4] != b"BILD":
        raise ValueError("not a BILD file")
    r.o = 4
    version = r.i32()
    if version not in (5, 6):
        raise ValueError(f"unsupported BILD version {version}")

    numsymbols = r.u32()
    _numframes = r.u32()
    name = r.string()
    numatlases = r.u32()
    atlases = [r.string() for _ in range(numatlases)]

    symbols = {}
    for _ in range(numsymbols):
        h = r.u32()
        sym = Symbol(hash=h)
        nframes = r.u32()
        for _i in range(nframes):
            framenum = r.u32()
            duration = r.u32()
            bbox = (r.f32(), r.f32(), r.f32(), r.f32())
            alphaidx = r.u32()
            alphacount = r.u32()
            sym.frames.append(SymbolFrame(framenum, duration, bbox, alphaidx, alphacount))
        symbols[h] = sym

    _alphaverts = r.u32()

    # vertex data is stored in ascending hash order
    for sym in sorted(symbols.values(), key=lambda s: s.hash):
        for fr in sym.frames:
            ntris = fr.alphacount // 3
            for _t in range(ntris):
                for _v in range(3):
                    fr.verts.append(
                        (r.f32(), r.f32(), r.f32(), r.f32(), r.f32(), r.f32())
                    )

    if version >= 6:
        htsize = r.u32()
        for _ in range(htsize):
            h = r.u32()
            if h in symbols:
                symbols[h].name = r.string()
            else:
                r.skip_string()
    else:
        for sym in symbols.values():
            sym.name = "symbol_%x" % sym.hash

    return Build(name=name, atlases=atlases, symbols=symbols)


# --------------------------------------------------------------------------- #
# anim (ANIM)
# --------------------------------------------------------------------------- #
@dataclass
class Element:
    hash: int
    build_frame: int
    layername_hash: int
    m: tuple             # (a, b, c, d, tx, ty)
    z: float
    name: str = ""
    layername: str = ""

    def transform(self, x: float, y: float):
        a, b, c, d, tx, ty = self.m
        return (a * x + c * y + tx, b * x + d * y + ty)


@dataclass
class AnimFrame:
    bbox: tuple
    events: list = field(default_factory=list)
    elements: list = field(default_factory=list)


@dataclass
class Anim:
    name: str
    facing: int
    bank_hash: int
    frame_rate: float
    frames: list = field(default_factory=list)
    bank: str = ""

    @property
    def duration(self) -> float:
        return len(self.frames) / self.frame_rate if self.frame_rate else 0.0


def parse_anim(data: bytes):
    r = Reader(data)
    if data[0:4] != b"ANIM":
        raise ValueError("not an ANIM file")
    r.o = 4
    version = r.i32()
    if version < 4:
        raise ValueError(f"unsupported ANIM version {version}")

    r.u32(); r.u32(); r.u32()
    numanims = r.u32()

    anims = []
    for _ in range(numanims):
        name = r.string()
        facing = r.u8()
        bank_hash = r.u32()
        frame_rate = r.f32()
        nframes = r.u32()
        anim = Anim(name=name, facing=facing, bank_hash=bank_hash, frame_rate=frame_rate)
        for _f in range(nframes):
            bbox = (r.f32(), r.f32(), r.f32(), r.f32())
            nevents = r.u32()
            events = [r.u32() for _e in range(nevents)]
            nelems = r.u32()
            elements = []
            for _el in range(nelems):
                h = r.u32()
                build_frame = r.u32()
                layer_hash = r.u32()
                mat = (r.f32(), r.f32(), r.f32(), r.f32(), r.f32(), r.f32())
                z = r.f32()
                elements.append(Element(h, build_frame, layer_hash, mat, z))
            anim.frames.append(AnimFrame(bbox, events, elements))
        anims.append(anim)

    htsize = r.u32()
    table = {}
    for _ in range(htsize):
        h = r.u32()
        table[h] = r.string()
    for anim in anims:
        anim.bank = table.get(anim.bank_hash, "")
        for fr in anim.frames:
            for el in fr.elements:
                el.name = table.get(el.hash, "elem_%x" % el.hash)
                el.layername = table.get(el.layername_hash, "")
    return anims, table, version


# --------------------------------------------------------------------------- #
# convenience
# --------------------------------------------------------------------------- #
def load_from_zip(zip_path: str):
    """Load build.bin/anim.bin from one of the game's anim/*.zip archives."""
    with zipfile.ZipFile(zip_path) as z:
        names = z.namelist()
        build = parse_build(z.read("build.bin")) if "build.bin" in names else None
        anims = parse_anim(z.read("anim.bin")) if "anim.bin" in names else None
    return build, anims


def load_build_from_zip(zip_path: str) -> Build:
    with zipfile.ZipFile(zip_path) as z:
        return parse_build(z.read("build.bin"))


def load_anim_from_zip(zip_path: str):
    with zipfile.ZipFile(zip_path) as z:
        return parse_anim(z.read("anim.bin"))


def find_anim(anims, name: str):
    """Return (anim, index) for a name, ignoring facing suffixes such as _left."""
    for i, a in enumerate(anims):
        if a.name == name:
            return a, i
    for i, a in enumerate(anims):
        if a.name.split("_")[0] == name:
            return a, i
    for i, a in enumerate(anims):
        if a.name.startswith(name):
            return a, i
    return None, None
