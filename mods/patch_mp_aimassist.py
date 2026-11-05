#!/usr/bin/env python3
"""Aim assist do Zombies no multiplayer do BO2 Requiem NX (patch in-place do t6mp.nro).

1. AimAssist_IsAutoAimActive() só retorna verdadeiro com o bit SESSIONMODE_ZOMBIES
   (0x10) ligado, e no t6mp ele nunca liga. O `tbz w3, #4` vira `nop`, liberando
   o auto-aim do ADS no MP.
2. aim_lockon_enabled (a mira acompanhar o alvo em movimento) é registrado com
   padrão 0 no PC. O `mov w1, #0` do registro vira `mov w1, #1`.
   Não dá para fazer isso por script: esses dvars não têm nome no executável de PC,
   e setdvar/setsaveddvar ignoram dvars sem nome.
3. AimAssist_GetAutoAimRange() devolve autoAimRange da arma * aim_autoAimRangeScale.
   Quando isso dá 0, só o Zombies com Deadshot recebe 4096. O patch tira essas
   condições: alcance 0 vira 4096 em qualquer modo (alcance diferente de 0 não muda).

Tudo é feito dentro do t6mp_guest.elf embutido no romfs (mesmo tamanho).

Uso: python3 patch_mp_aimassist.py caminho/para/t6mp.nro [saida.nro]
Sem [saida.nro], grava por cima e deixa um .bak do original.
"""
import shutil
import struct
import sys

GUEST = "t6mp_guest.elf"
NOP = 0xD503201F
MOV_W1_0 = 0x52800001  # mov w1, #0
MOV_W1_1 = 0x52800021  # mov w1, #1
LOCKON = "aim_lockon_enabled"
# AimAssist_GetAutoAimRange: ldr s31,[x2,#0x570] ... fcmp s31,s0; b.ne ... mov w0,#4096.0; fmov s0,w0
RANGE_SIG = {0: 0xBD45705F, 3: 0x1E3F0800, 5: 0x1E2023E0, 6: 0x54000121, 32: 0x52A8B000, 33: 0x1E270000}
RANGE_CONST_LOAD = (4, 0xBD40001F, 0x1E2703FF)  # ldr s31, [x0]  ->  fmov s31, wzr (compara com 0.0)
RANGE_SKIP = (7, 0x90000000, 0x14000019)        # adrp x0, ...   ->  b +0x64 (direto para o 4096.0)


def romfs_file(nro, name):
    if nro[0x10:0x14] != b"NRO0":
        raise SystemExit("não é um NRO")
    aset = struct.unpack_from("<I", nro, 0x18)[0]
    if nro[aset:aset + 4] != b"ASET":
        raise SystemExit("NRO sem seção ASET/romfs")
    rom_off = struct.unpack_from("<Q", nro, aset + 8 + 32)[0]
    rom = aset + rom_off
    _, _, _, _, _, _, _, fm_off, fm_size, data_off = struct.unpack_from("<10Q", nro, rom)
    pos = 0
    while pos < fm_size:
        _, _, foff, fsize, _, nlen = struct.unpack_from("<IIQQII", nro, rom + fm_off + pos)
        fname = nro[rom + fm_off + pos + 32:rom + fm_off + pos + 32 + nlen].decode()
        if fname == name:
            return rom + data_off + foff, fsize
        pos += 32 + ((nlen + 3) & ~3)
    raise SystemExit(f"{name} não encontrado no romfs")


class Guest:
    """ELF32 AArch64 (ILP32) dentro do NRO; offsets devolvidos são do NRO."""

    def __init__(self, nro, start):
        self.nro, self.start = nro, start
        shoff, = struct.unpack_from("<I", nro, start + 0x20)
        shentsize, shnum, shstrndx = struct.unpack_from("<HHH", nro, start + 0x2E)
        secs = []
        for i in range(shnum):
            sname, _, _, addr, off, size = struct.unpack_from("<IIIIII", nro, start + shoff + i * shentsize)
            secs.append((sname, addr, off, size))
        strtab = start + secs[shstrndx][2]
        self.secs = {}
        for sname, addr, off, size in secs:
            end = nro.index(b"\0", strtab + sname)
            self.secs[nro[strtab + sname:end].decode()] = (addr, off, size)

    def word(self, off):
        return struct.unpack_from("<I", self.nro, off)[0]

    def text_words(self):
        addr, off, size = self.secs[".text"]
        return [(addr + i, self.start + off + i) for i in range(0, size, 4)]

    def rodata_strings(self, s):
        """Endereços de todas as cópias da string (o rodata tem duplicatas)."""
        addr, off, size = self.secs[".rodata"]
        lo, hi = self.start + off, self.start + off + size
        needle = b"\0" + s.encode() + b"\0"
        found, out = lo - 1, []
        while True:
            found = self.nro.find(needle, found + 1, hi)
            if found < 0:
                break
            out.append(addr + (found + 1 - lo))
        if not out:
            raise SystemExit(f"string {s!r} não encontrada; versão não suportada")
        return out


def find_gate(g, words):
    """Offsets do `tbz w3, #4` de AimAssist_IsAutoAimActive, e de um nop já aplicado."""
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
    """Offset do início do trecho de AimAssist_GetAutoAimRange (original ou já patchado)."""
    hits = []
    for _, off in words[:-40]:
        if all(g.word(off + 4 * i) == v for i, v in RANGE_SIG.items()):
            hits.append(off)
    if len(hits) != 1:
        raise SystemExit(f"AimAssist_GetAutoAimRange encontrado {len(hits)} vezes; versão não suportada")
    return hits[0]


def find_bool_default(g, words, name):
    """Offset do `mov w1, #padrão` na chamada que registra o dvar `name`."""
    targets = {(va & ~0xFFF, va & 0xFFF) for va in g.rodata_strings(name)}
    is_bl = lambda m: (g.word(words[m][1]) & 0xFC000000) == 0x94000000
    sites = set()
    for k, (pc, off) in enumerate(words):
        ins = g.word(off)
        if (ins & 0x9F000000) != 0x90000000:  # adrp
            continue
        rd = ins & 31
        imm = (((ins >> 5) & 0x7FFFF) << 2) | ((ins >> 29) & 3)
        if imm & (1 << 20):
            imm -= 1 << 21
        page = (pc & ~0xFFF) + (imm << 12)
        for j in range(k + 1, min(k + 12, len(words))):
            a = g.word(words[j][1])
            # add w0, w<rd>, #lo
            if (a & 0xFFC003FF) != (0x11000000 | (rd << 5)) or (page, (a >> 10) & 0xFFF) not in targets:
                continue
            call = next((m for m in range(j + 1, min(j + 40, len(words))) if is_bl(m)), None)
            if call is None:
                break
            # o mov w1 pode vir antes ou depois do add do nome; vale o último antes do bl
            for m in range(call - 1, max(call - 60, 0), -1):
                if is_bl(m):
                    break
                if g.word(words[m][1]) in (MOV_W1_0, MOV_W1_1):
                    sites.add(words[m][1])
                    break
            break
    if len(sites) != 1:
        raise SystemExit(f"registro de {name} encontrado {len(sites)} vezes; versão não suportada")
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
        struct.pack_into("<I", nro, hits[0], NOP)
        changes.append(f"auto-aim do ADS liberado (+0x{hits[0] - start:x})")
    elif not (patched and not hits):
        raise SystemExit(f"assinatura do auto-aim encontrada {len(hits)} vezes (esperado 1); versão não suportada")

    off = find_bool_default(g, words, LOCKON)
    if g.word(off) == MOV_W1_0:
        struct.pack_into("<I", nro, off, MOV_W1_1)
        changes.append(f"{LOCKON} ligado por padrão (+0x{off - start:x})")

    base = find_range(g, words)
    for idx, orig, new in (RANGE_CONST_LOAD, RANGE_SKIP):
        cur = g.word(base + 4 * idx)
        if cur == new:
            continue
        if (cur if idx != RANGE_SKIP[0] else cur & 0x9F00001F) != orig:
            raise SystemExit("AimAssist_GetAutoAimRange diferente do esperado; versão não suportada")
        struct.pack_into("<I", nro, base + 4 * idx, new)
        changes.append(f"alcance do auto-aim: instrução +0x{base + 4 * idx - start:x}")

    if not changes:
        print("já está patchado; nada a fazer")
        return
    if dst == src:
        shutil.copyfile(src, src + ".bak")
    with open(dst, "wb") as f:
        f.write(nro)
    print("\n".join(changes))
    print(f"-> {dst}")


if __name__ == "__main__":
    main()
