#!/usr/bin/env python3
"""In-game FPS counter with frametime: "60 fps  16.6 ms  max 33 ms".

The Requiem NX counter (enabled in Options > "Show FPS", dvar cg_drawFPS) keeps the
times of the last 32 frames in a ring buffer but only shows "%i fps". The patch replaces
the va("%i fps", fps) call with a new function that walks the same buffer and formats
FPS, average frametime and the worst frame in the window (a stutter spike stays on
screen for ~0.5 s).

The function and the string go in the free space between the end of the first PT_LOAD
(R+X) of t6*_guest.elf and the next page; that segment's p_filesz/p_memsz grows to
cover them. Works for t6mp.nro and t6zm.nro. File size is unchanged.

Usage: python3 patch_fps_counter.py path/to/t6mp.nro [output.nro]
Without [output.nro], overwrites in place and keeps a .bak of the original.
"""
import struct
import sys

from nro_guest import (Guest, adrp_target, bl_target, enc_adrp, enc_add_w, enc_b, enc_bcond,
                       enc_bl, find_guest, write_nro)

FMT = b"%i fps  %i.%i ms  max %i ms\0"
GE = 0xA
FSUB_S0 = 0x1E3E3BE0   # fsub s0, s31, s30
STR_S0 = 0xBD0073E0    # str s0, [sp, #0x70]


def find_site(g):
    """(offset of the bl va, VA of the bl, VA of va(), VA of the frametime buffer)."""
    sites = []
    fmt_vas = set(g.rodata_strings("%i fps"))
    for pc, off in g.text_words():
        page = adrp_target(pc, g.word(off))
        if page is None or (g.word(off) & 31) != 0:
            continue
        add = g.word(off + 4)
        if (add & 0xFFC003FF) != 0x11000000 or page + ((add >> 10) & 0xFFF) not in fmt_vas:
            continue
        if g.word(off + 8) != FSUB_S0 or g.word(off + 12) != STR_S0:
            continue
        call_pc = pc + 16
        callee = bl_target(call_pc, g.word(off + 16))
        # buffer: adrp x0 / add w0, w0, #lo 0x74 bytes before the format adrp
        b_adrp, b_add = g.word(off - 0x74), g.word(off - 0x70)
        bpage = adrp_target(pc - 0x74, b_adrp)
        if callee is None or bpage is None or (b_add & 0xFFC003FF) != 0x11000000:
            continue
        buf = bpage + ((b_add >> 10) & 0xFFF)
        # the counter sits 8 bytes before it: str w2, [x4, #(buf-8)&0xfff]
        if g.word(off - 0x94) != (0xB9000082 | ((((buf - 8) & 0xFFF) // 4) << 10)):
            continue
        sites.append((off + 16, call_pc, callee, buf))
    if len(sites) != 1:
        raise SystemExit(f"FPS counter found {len(sites)} times; unsupported version")
    return sites[0]


def build_cave(cave, va, buf):
    """Takes w1 = fps and ends with a tail call to va(fmt, fps, ms, tenths, max).

    No stack frame: only uses x0, x2-x4 and x9-x15 (caller-saved) and leaves w1 alone.
    """
    code = []
    pc = lambda: cave + 4 * len(code)
    code.append(enc_adrp(9, pc(), buf - 8))
    code += [0xB940012A | ((((buf - 8) & 0xFFF) // 4) << 10),  # ldr w10, [x9, #count]
             0x5280040B,              # mov w11, #32
             0x7100815F,              # cmp w10, #32
             0x1A8BD14A]              # csel w10, w10, w11, le   (n = min(count, 32))
    code.append(enc_add_w(9, 9, buf & 0xFFF))
    code += [0x5280000C,              # mov w12, #0              (sum)
             0x5280000D,              # mov w13, #0              (max)   
             0x5280000E]              # mov w14, #0              (i)
    loop = pc()
    code.append(0x6B0A01DF)           # cmp w14, w10
    bge = len(code)
    code.append(0)
    code += [0xB86E592F,              # ldr w15, [x9, w14, uxtw #2]
             0x0B0F018C,              # add w12, w12, w15
             0x6B0D01FF,              # cmp w15, w13
             0x1A8DC1ED,              # csel w13, w15, w13, gt
             0x110005CE]              # add w14, w14, #1
    code.append(enc_b(pc(), loop))
    code[bge] = enc_bcond(loop + 4, pc(), GE)
    code += [0x5280014F,              # mov w15, #10
             0x1B0F7D8C,              # mul w12, w12, w15
             0x1ACA098C,              # udiv w12, w12, w10       (average in tenths of ms)
             0x1ACF0982,              # udiv w2, w12, w15
             0x1B0FB043,              # msub w3, w2, w15, w12
             0x2A0D03E4]              # mov w4, w13
    fmt_at = len(code)
    code += [0, 0]
    code.append(enc_b(pc(), va))      # tail call: va() returns straight to the caller
    fmt_va = pc()
    code[fmt_at] = enc_adrp(0, cave + 4 * fmt_at, fmt_va)
    code[fmt_at + 1] = enc_add_w(0, 0, fmt_va & 0xFFF)
    return b"".join(struct.pack("<I", w) for w in code) + FMT


def main():
    if len(sys.argv) not in (2, 3):
        raise SystemExit(__doc__)
    src = sys.argv[1]
    dst = sys.argv[2] if len(sys.argv) == 3 else src
    nro = bytearray(open(src, "rb").read())
    name, start = find_guest(nro)
    g = Guest(nro, start)

    call_off, call_pc, callee, buf = find_site(g)
    if callee >= g.secs[".eh_frame"][0] + g.secs[".eh_frame"][2]:
        print("already patched; nothing to do")
        return

    cave = g.next_code_va(4)
    g.append_code(build_cave(cave, callee, buf), 4)
    g.put(call_off, enc_bl(call_pc, cave))

    write_nro(nro, src, dst, [
        f"{name}: FPS counter with frametime (function at 0x{cave:x}, called at 0x{call_pc:x})",
    ])


if __name__ == "__main__":
    main()
