#!/usr/bin/env python3
"""Zombies aim assist in BO2 Requiem NX multiplayer (in-place patch of t6mp.nro).

1. AimAssist_IsAutoAimActive() only returns true with the SESSIONMODE_ZOMBIES bit
   (0x10) set, which never happens in t6mp. The `tbz w3, #4` becomes a `nop`,
   enabling ADS auto-aim in MP.
2. aim_lockon_enabled (the reticle tracking a moving target) is registered with
   default 0 on PC. The registration's `mov w1, #0` becomes `mov w1, #1`.
   This cannot be done from a script: these dvars have no name in the PC executable,
   and setdvar/setsaveddvar ignore unnamed dvars.
3. AimAssist_GetAutoAimRange() returns the weapon's autoAimRange * aim_autoAimRangeScale.
   When that is 0, only Zombies with Deadshot gets 4096. The patch removes those
   conditions: a range of 0 becomes 4096 in any mode (nonzero ranges are unchanged).

Everything happens inside the t6mp_guest.elf embedded in the romfs (same size).

Usage: python3 patch_mp_aimassist.py path/to/t6mp.nro [output.nro]
Without [output.nro], overwrites in place and keeps a .bak of the original.
"""
import sys

from nro_guest import Guest, adrp_target, bl_target, romfs_file, write_nro

GUEST = "t6mp_guest.elf"
NOP = 0xD503201F
MOV_W1_0 = 0x52800001  # mov w1, #0
MOV_W1_1 = 0x52800021  # mov w1, #1
LOCKON = "aim_lockon_enabled"
# AimAssist_GetAutoAimRange: ldr s31,[x2,#0x570] ... fcmp s31,s0; b.ne ... mov w0,#4096.0; fmov s0,w0
RANGE_SIG = {0: 0xBD45705F, 3: 0x1E3F0800, 5: 0x1E2023E0, 6: 0x54000121, 32: 0x52A8B000, 33: 0x1E270000}
RANGE_CONST_LOAD = (4, 0xBD40001F, 0x1E2703FF)  # ldr s31, [x0]  ->  fmov s31, wzr (compare with 0.0)
RANGE_SKIP = (7, 0x90000000, 0x14000019)        # adrp x0, ...   ->  b +0x64 (straight to the 4096.0)


def find_gate(g, words):
    """Offsets of the `tbz w3, #4` in AimAssist_IsAutoAimActive, and of an already applied nop."""
    hits, patched = [], []
    for _, off in words[4:-3]:
        w = lambda i: g.word(off + 4 * i)
        if not (w(-4) == 0x39400860                       # ldrb w0, [x3, #2]
                and (w(-3) & 0xFFF8001F) == 0x37000000    # tbnz w0, #0, ...
                and w(1) == 0xB9402483                    # ldr  w3, [x4, #0x24]
                and (w(2) & 0xFFF8001F) == 0x36A00003):   # tbz  w3, #0x14, ...
            continue
        if (w(0) & 0xFFF8001F) == 0x36200003:             # tbz  w3, #4, ...
            hits.append(off)
        elif w(0) == NOP:
            patched.append(off)
    return hits, patched


def find_range(g, words):
    """Offset of the start of the AimAssist_GetAutoAimRange sequence (original or already patched)."""
    hits = [off for _, off in words[:-40] if all(g.word(off + 4 * i) == v for i, v in RANGE_SIG.items())]
    if len(hits) != 1:
        raise SystemExit(f"AimAssist_GetAutoAimRange found {len(hits)} times; unsupported version")
    return hits[0]


def find_bool_default(g, words, name):
    """Offset of the `mov w1, #default` in the call that registers dvar `name`."""
    targets = {(va & ~0xFFF, va & 0xFFF) for va in g.rodata_strings(name)}
    is_bl = lambda m: bl_target(words[m][0], g.word(words[m][1])) is not None
    sites = set()
    for k, (pc, off) in enumerate(words):
        ins = g.word(off)
        page = adrp_target(pc, ins)
        if page is None:
            continue
        rd = ins & 31
        for j in range(k + 1, min(k + 12, len(words))):
            a = g.word(words[j][1])
            # add w0, w<rd>, #lo
            if (a & 0xFFC003FF) != (0x11000000 | (rd << 5)) or (page, (a >> 10) & 0xFFF) not in targets:
                continue
            call = next((m for m in range(j + 1, min(j + 40, len(words))) if is_bl(m)), None)
            if call is None:
                break
            # the mov w1 may come before or after the name add; the last one before the bl wins
            for m in range(call - 1, max(call - 60, 0), -1):
                if is_bl(m):
                    break
                if g.word(words[m][1]) in (MOV_W1_0, MOV_W1_1):
                    sites.add(words[m][1])
                    break
            break
    if len(sites) != 1:
        raise SystemExit(f"registration of {name} found {len(sites)} times; unsupported version")
    return sites.pop()


def main():
    if len(sys.argv) not in (2, 3):
        raise SystemExit(__doc__)
    src = sys.argv[1]
    dst = sys.argv[2] if len(sys.argv) == 3 else src
    nro = bytearray(open(src, "rb").read())
    start, _ = romfs_file(nro, GUEST)
    g = Guest(nro, start)
    words = g.text_words()

    changes = []
    hits, patched = find_gate(g, words)
    if len(hits) == 1:
        g.put(hits[0], NOP)
        changes.append(f"ADS auto-aim enabled (+0x{hits[0] - start:x})")
    elif not (patched and not hits):
        raise SystemExit(f"auto-aim signature found {len(hits)} times (expected 1); unsupported version")

    off = find_bool_default(g, words, LOCKON)
    if g.word(off) == MOV_W1_0:
        g.put(off, MOV_W1_1)
        changes.append(f"{LOCKON} enabled by default (+0x{off - start:x})")

    base = find_range(g, words)
    for idx, orig, new in (RANGE_CONST_LOAD, RANGE_SKIP):
        cur = g.word(base + 4 * idx)
        if cur == new:
            continue
        if (cur if idx != RANGE_SKIP[0] else cur & 0x9F00001F) != orig:
            raise SystemExit("AimAssist_GetAutoAimRange differs from expected; unsupported version")
        g.put(base + 4 * idx, new)
        changes.append(f"auto-aim range: instruction +0x{base + 4 * idx - start:x}")

    write_nro(nro, src, dst, changes)


if __name__ == "__main__":
    main()
