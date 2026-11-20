#!/usr/bin/env python3
"""Zombies aim assist in BO2 Requiem NX multiplayer (in-place patch of t6mp.nro).

1. AimAssist_IsAutoAimActive() only returns true with the SESSIONMODE_ZOMBIES bit
   (0x10) set, which never happens in t6mp. The `tbz w3, #4` becomes a branch to
   aim_gate/aim_gate.bin, which enables ADS auto-aim in MP only while this console runs
   the server (sv_running) and the dvar nx_aimassist_allowed is nonzero. The script
   scripts/mp/aim_assist_bots_only.gsc sets that dvar on the host: 1 while every other
   player is a bot (or local to the host), 0 as soon as a remote human joins. Without the
   script, auto-aim stays off in MP. The session mode cannot be used for this: the port's
   online play runs as SESSIONMODE_SYSTEMLINK, like Solo and Private Match.
   NROs patched by older versions (a `nop` there) are converted to the gate.
2. aim_lockon_enabled (the reticle tracking a moving target) is registered with
   default 0 on PC. The registration's `mov w1, #0` becomes `mov w1, #1`.
   This cannot be done from a script: these dvars have no name in the PC executable,
   and setdvar/setsaveddvar ignore unnamed dvars.
3. AimAssist_GetAutoAimRange() returns the weapon's autoAimRange * aim_autoAimRangeScale.
   When that is 0, only Zombies with Deadshot gets 4096. The patch removes those
   conditions: a range of 0 becomes 4096 in any mode (nonzero ranges are unchanged).

Everything happens inside the t6mp_guest.elf embedded in the romfs (same size). The gate
goes in the free space after the code segment (like patch_fps_counter.py) and uses 8
bytes after .bss.

Usage: python3 patch_mp_aimassist.py path/to/t6mp.nro [output.nro]
Without [output.nro], overwrites in place and keeps a .bak of the original.
"""
import os
import struct
import sys

from nro_guest import (Guest, adrp_target, b_target, bl_target, djb2, enc_b, find_dvar_find, romfs_file,
                       write_nro)

GUEST = "t6mp_guest.elf"
GATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "aim_gate", "aim_gate.bin")
GATE_ALLOW, GATE_DENY, GATE_ENTRY = 0x18, 0x1C, 0x20
GATE_STATE = 8
ALLOWED_DVAR = "nx_aimassist_allowed"
NOP = 0xD503201F
MOV_W1_0 = 0x52800001  # mov w1, #0
MOV_W1_1 = 0x52800021  # mov w1, #1
LOCKON = "aim_lockon_enabled"
# AimAssist_GetAutoAimRange: ldr s31,[x2,#0x570] ... fcmp s31,s0; b.ne ... mov w0,#4096.0; fmov s0,w0
RANGE_SIG = {0: 0xBD45705F, 3: 0x1E3F0800, 5: 0x1E2023E0, 6: 0x54000121, 32: 0x52A8B000, 33: 0x1E270000}
RANGE_CONST_LOAD = (4, 0xBD40001F, 0x1E2703FF)  # ldr s31, [x0]  ->  fmov s31, wzr (compare with 0.0)
RANGE_SKIP = (7, 0x90000000, 0x14000019)        # adrp x0, ...   ->  b +0x64 (straight to the 4096.0)
# Dvar_GetInt: mov w1,w0; cbz; ldr w0,[x1,#0x10]; sub w2,w0,#6; cmp w2,#1; b.ls; cmp w0,#1; b.eq;
#              cmp w0,#2; b.eq; ldr w0,[x1,#0x18]; b atoi; ldr w0,[x1,#0x18]; ret
DVAR_INT_SIG = {0: 0x2A0003E1, 2: 0xB9401020, 3: 0x51001802, 4: 0x7100045F, 6: 0x7100041F,
                8: 0x7100081F, 10: 0xB9401820, 12: 0xB9401820, 13: 0xD65F03C0}


def tb_target(pc, ins):
    imm = (ins >> 5) & 0x3FFF
    if imm & (1 << 13):
        imm -= 1 << 14
    return pc + imm * 4


def find_gate(g, words):
    """(offset, VA, VA of the stock exit, state) of the session check in AimAssist_IsAutoAimActive.

    state: "stock" (`tbz w3, #4`), "nop" (older version of this patch) or "gate" (already patched).
    """
    code_end = g.secs[".eh_frame"][0] + g.secs[".eh_frame"][2]
    sites = []
    for pc, off in words[4:-3]:
        w = lambda i: g.word(off + 4 * i)
        if not (w(-4) == 0x39400860                       # ldrb w0, [x3, #2]
                and (w(-3) & 0xFFF8001F) == 0x37000000    # tbnz w0, #0, ...
                and w(1) == 0xB9402483                    # ldr  w3, [x4, #0x24]
                and (w(2) & 0xFFF8001F) == 0x36A00003):   # tbz  w3, #0x14, <exit>
            continue
        exit_va = tb_target(pc + 8, w(2))                 # same `ret` as the session check
        if (w(0) & 0xFFF8001F) == 0x36200003 and tb_target(pc, w(0)) == exit_va:  # tbz w3, #4, <exit>
            sites.append((off, pc, exit_va, "stock"))
        elif w(0) == NOP:
            sites.append((off, pc, exit_va, "nop"))
        elif (b_target(pc, w(0)) or 0) >= code_end:
            sites.append((off, pc, exit_va, "gate"))
    if len(sites) != 1:
        raise SystemExit(f"auto-aim signature found {len(sites)} times (expected 1); unsupported version")
    return sites[0]


def find_dvar_int(g, words):
    """Dvar_GetInt(dvar_t *): reads bool, int, float and (with atoi) string dvars."""
    hits = [pc for k, (pc, off) in enumerate(words[:-14])
            if all(g.word(off + 4 * i) == v for i, v in DVAR_INT_SIG.items())]
    if len(hits) != 1:
        raise SystemExit(f"Dvar_GetInt found {len(hits)} times; unsupported version")
    return hits[0]


def install_gate(g, words, off, pc, exit_va):
    blob = bytearray(open(GATE, "rb").read())
    cave = g.next_code_va(16)
    state = g.alloc_bss(GATE_STATE)
    dvar_find, dvar_int = find_dvar_find(g, words), find_dvar_int(g, words)
    struct.pack_into("<6I", blob, 0, dvar_find, dvar_int, state, djb2("sv_running"), djb2(ALLOWED_DVAR), cave)
    struct.pack_into("<II", blob, GATE_ALLOW, enc_b(cave + GATE_ALLOW, pc + 4), enc_b(cave + GATE_DENY, exit_va))
    g.append_code(blob, 16)
    g.put(off, enc_b(pc, cave + GATE_ENTRY))
    return (f"ADS auto-aim in MP only on the host with bots (gate at 0x{cave:x}, state 0x{state:x},"
            f" from 0x{pc:x}; Dvar_FindVarByHash 0x{dvar_find:x}, Dvar_GetInt 0x{dvar_int:x})")


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
    off, pc, exit_va, state = find_gate(g, words)
    if state != "gate":
        changes.append(install_gate(g, words, off, pc, exit_va))

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
