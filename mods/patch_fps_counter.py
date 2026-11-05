#!/usr/bin/env python3
"""Contador de FPS do jogo com frametime: "60 fps  16.6 ms  max 33 ms".

O contador do Requiem NX (liga em Opções > "Mostrar FPS", dvar cg_drawFPS) guarda o
tempo dos últimos 32 quadros num buffer circular e só mostra "%i fps". O patch troca a
chamada va("%i fps", fps) por uma função nova que percorre o mesmo buffer e formata
FPS, frametime médio e o pior quadro da janela (o pico de um stutter fica ~0,5 s na tela).

A função e a string vão no espaço livre entre o fim do primeiro PT_LOAD (R+X) do
t6*_guest.elf e a próxima página; o p_filesz/p_memsz desse segmento cresce para cobri-las.
Serve para t6mp.nro e t6zm.nro. Mesmo tamanho de arquivo.

Uso: python3 patch_fps_counter.py caminho/para/t6mp.nro [saida.nro]
Sem [saida.nro], grava por cima e deixa um .bak do original.
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
    """(offset do bl va, VA do bl, VA de va(), VA do buffer de frametimes)."""
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
        # buffer: adrp x0 / add w0, w0, #lo 0x74 bytes antes do adrp do formato
        b_adrp, b_add = g.word(off - 0x74), g.word(off - 0x70)
        bpage = adrp_target(pc - 0x74, b_adrp)
        if callee is None or bpage is None or (b_add & 0xFFC003FF) != 0x11000000:
            continue
        buf = bpage + ((b_add >> 10) & 0xFFF)
        # o contador fica 8 bytes antes: str w2, [x4, #(buf-8)&0xfff]
        if g.word(off - 0x94) != (0xB9000082 | ((((buf - 8) & 0xFFF) // 4) << 10)):
            continue
        sites.append((off + 16, call_pc, callee, buf))
    if len(sites) != 1:
        raise SystemExit(f"contador de FPS encontrado {len(sites)} vezes; versão não suportada")
    return sites[0]


def build_cave(cave, va, buf):
    """Recebe w1 = fps e termina com tail call em va(fmt, fps, ms, décimos, max).

    Sem frame próprio: só usa x0, x2-x4 e x9-x15 (caller-saved) e não toca em w1.
    """
    code = []
    pc = lambda: cave + 4 * len(code)
    code.append(enc_adrp(9, pc(), buf - 8))
    code += [0xB940012A | ((((buf - 8) & 0xFFF) // 4) << 10),  # ldr w10, [x9, #count]
             0x5280040B,              # mov w11, #32
             0x7100815F,              # cmp w10, #32
             0x1A8BD14A]              # csel w10, w10, w11, le   (n = min(count, 32))
    code.append(enc_add_w(9, 9, buf & 0xFFF))
    code += [0x5280000C,              # mov w12, #0              (soma)
             0x5280000D,              # mov w13, #0              (máximo)
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
             0x1ACA098C,              # udiv w12, w12, w10       (média em décimos de ms)
             0x1ACF0982,              # udiv w2, w12, w15
             0x1B0FB043,              # msub w3, w2, w15, w12
             0x2A0D03E4]              # mov w4, w13
    fmt_at = len(code)
    code += [0, 0]
    code.append(enc_b(pc(), va))      # tail call: va() volta direto para o chamador
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

    # primeiro PT_LOAD: text + rodata + eh_frame (R+X)
    ph = next(p for p in g.phdrs if struct.unpack_from("<I", nro, p)[0] == 1)
    _, seg_off, seg_va, _, filesz, memsz, flags, _ = struct.unpack_from("<8I", nro, ph)
    if not flags & 1 or seg_off != 0 or filesz != memsz:
        raise SystemExit("primeiro segmento do guest inesperado; versão não suportada")
    call_off, call_pc, callee, buf = find_site(g)
    seg_end = seg_va + filesz

    if callee >= g.secs[".eh_frame"][0] + g.secs[".eh_frame"][2]:
        print("já está patchado; nada a fazer")
        return

    cave = (seg_end + 3) & ~3
    blob = build_cave(cave, callee, buf)
    end = cave + len(blob)
    if end > (seg_end + 0xFFF) & ~0xFFF:
        raise SystemExit("sem espaço livre no fim do segmento")
    raw = start + seg_off + (cave - seg_va)
    if any(nro[start + seg_off + (seg_end - seg_va):raw + len(blob)]):
        raise SystemExit("espaço depois do segmento não está zerado; versão não suportada")
    nro[raw:raw + len(blob)] = blob
    struct.pack_into("<II", nro, ph + 16, end - seg_va, end - seg_va)
    g.put(call_off, enc_bl(call_pc, cave))

    write_nro(nro, src, dst, [
        f"{name}: contador de FPS com frametime (função em 0x{cave:x}, chamada em 0x{call_pc:x})",
    ])


if __name__ == "__main__":
    main()
