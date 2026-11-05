#!/usr/bin/env python3
"""Log automático de desempenho no t6mp.log (só multiplayer).

Liga o perf_log/perf_log.bin (fonte em perf_log/perf_log.c) na chamada que o SCR do
port faz uma vez por quadro para ler cg_drawFPS. O t6mp.log passa a receber:

  [perf] t=123456 ms: 597 quadros, media 16.77 ms, max 60.0 ms, >=20ms 1, >=34ms 1,
         >=50ms 1, >=100ms 0, vsync 1, maxfps 60, log 850 us     (a cada 10 s)
  [perf] hitch 60 ms em t=123000 ms                               (quadros >= 50 ms, até 4 por janela)

"t" usa o mesmo relógio das linhas "[load] %u ms" do próprio port, para cruzar eventos.
"log" é o pior tempo gasto escrevendo no log na janela anterior; esse tempo não entra
nas medições.

O código vai no espaço livre depois do primeiro PT_LOAD (como o patch_fps_counter.py);
o estado (64 bytes) vai logo depois do .bss, com p_memsz aumentado. No t6zm.nro não
sobra espaço depois do contador de FPS, por isso o script recusa.

Uso: python3 patch_perf_log.py caminho/para/t6mp.nro [saida.nro]
"""
import os
import struct
import sys

from nro_guest import Guest, adrp_target, bl_target, enc_bl, romfs_file, write_nro

GUEST = "t6mp_guest.elf"
BLOB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "perf_log", "perf_log.bin")
TBL_SIZE = 32
ENTRY = 0x20
STATE_SIZE = 0x40


def djb2(name):
    h = 5381
    for c in name.lower().encode():
        h = (c + 33 * h) & 0xFFFFFFFF
    return h


def string_ref(g, words, s):
    """Offsets dos `add w0, wN, #lo` que formam o endereço da string `s` (com o adrp antes)."""
    targets = set(g.rodata_strings(s))
    hits = []
    for k, (pc, off) in enumerate(words[:-1]):
        ins = g.word(off)
        page = adrp_target(pc, ins)
        if page is None:
            continue
        rd = ins & 31
        for j in range(k + 1, min(k + 12, len(words))):
            a = g.word(words[j][1])
            if (a & 0xFFC0001F) == 0x11000000 and ((a >> 5) & 31) == rd \
                    and page + ((a >> 10) & 0xFFF) in targets:
                hits.append(j)
                break
    return hits


def next_bls(g, words, j, count, limit=12):
    out = []
    for m in range(j + 1, min(j + limit, len(words))):
        t = bl_target(words[m][0], g.word(words[m][1]))
        if t is not None:
            out.append((m, t))
            if len(out) == count:
                return out
    raise SystemExit("chamadas esperadas não encontradas; versão não suportada")


def find_log_fns(g, words):
    """va() e nx_log() a partir de nx_log(va("[load] %u ms: zone %s done, %d assets", ...))."""
    refs = string_ref(g, words, "[load] %u ms: zone %s done, %d assets")
    if len(refs) != 1:
        raise SystemExit("linha [load] do port não encontrada; versão não suportada")
    (m1, va), (m2, nx_log) = next_bls(g, words, refs[0], 2, limit=6)
    if m2 != m1 + 1:
        raise SystemExit("chamada de log inesperada; versão não suportada")
    return va, nx_log


def find_dvar_find(g, words):
    """Dvar_FindVarByHash: em SetSavedDvar, `bl hash; bl find; mov w1, w0; cbz w0, ...`."""
    found = set()
    for j in string_ref(g, words, 'SetSavedDvar(): The dvar "%s" does not exist.'):
        for m in range(max(j - 200, 0), min(j + 200, len(words) - 3)):
            a, b = g.word(words[m][1]), g.word(words[m + 1][1])
            if bl_target(words[m][0], a) and bl_target(words[m + 1][0], b) \
                    and g.word(words[m + 2][1]) == 0x2A0003E1 \
                    and (g.word(words[m + 3][1]) & 0xFF00001F) == 0x34000000:
                found.add(bl_target(words[m + 1][0], b))
    if len(found) != 1:
        raise SystemExit(f"Dvar_FindVarByHash encontrado {len(found)} vezes; versão não suportada")
    return found.pop()


def find_hook(g, words):
    """(offset do bl, VA do bl, alvo atual) de Dvar_GetInt(cg_drawFPS) no SCR do port."""
    refs = string_ref(g, words, "cg_drawFPS")
    globals_ = set()
    for j in refs:
        (m, _), = next_bls(g, words, j, 1, limit=4)
        for n in range(m + 1, min(m + 8, len(words))):
            s = g.word(words[n][1])
            if (s & 0xFFC0001F) == 0xB9000000:  # str w0, [xN, #imm]
                rn = (s >> 5) & 31
                for p in range(n - 1, max(n - 8, 0), -1):
                    page = adrp_target(words[p][0], g.word(words[p][1]))
                    if page is not None and (g.word(words[p][1]) & 31) == rn:
                        globals_.add(page + ((s >> 10) & 0xFFF) * 4)
                        break
                break
    if len(globals_) != 1:
        raise SystemExit("dvar cg_drawFPS não encontrado; versão não suportada")
    gv = globals_.pop()
    sites = []
    for k, (pc, off) in enumerate(words[:-2]):
        if adrp_target(pc, g.word(off)) != gv & ~0xFFF or (g.word(off) & 31) != 0:
            continue
        ldr = g.word(words[k + 1][1])
        if ldr != (0xB9400000 | (((gv & 0xFFF) // 4) << 10)):  # ldr w0, [x0, #lo]
            continue
        t = bl_target(words[k + 2][0], g.word(words[k + 2][1]))
        if t is not None:
            sites.append((words[k + 2][1], words[k + 2][0], t))
    if len(sites) != 1:
        raise SystemExit(f"leitura de cg_drawFPS por quadro encontrada {len(sites)} vezes; versão não suportada")
    return sites[0]


def main():
    if len(sys.argv) not in (2, 3):
        raise SystemExit(__doc__)
    src = sys.argv[1]
    dst = sys.argv[2] if len(sys.argv) == 3 else src
    nro = bytearray(open(src, "rb").read())
    start, _ = romfs_file(nro, GUEST)
    g = Guest(nro, start)
    words = g.text_words()

    loads = [p for p in g.phdrs if struct.unpack_from("<I", nro, p)[0] == 1]
    ph_x, ph_rw = loads[0], loads[1]
    _, x_off, x_va, _, x_filesz, x_memsz, x_flags, _ = struct.unpack_from("<8I", nro, ph_x)
    _, _, rw_va, _, _, rw_memsz, rw_flags, _ = struct.unpack_from("<8I", nro, ph_rw)
    if not x_flags & 1 or x_off != 0 or x_filesz != x_memsz or not rw_flags & 2:
        raise SystemExit("segmentos do guest inesperados; versão não suportada")

    call_off, call_pc, callee = find_hook(g, words)
    x_end = x_va + x_filesz
    if callee >= g.secs[".eh_frame"][0] + g.secs[".eh_frame"][2]:
        print("já está patchado; nada a fazer")
        return

    va, nx_log = find_log_fns(g, words)
    dvar_find = find_dvar_find(g, words)

    blob = bytearray(open(BLOB, "rb").read())
    cave = (x_end + 15) & ~15
    end = cave + len(blob)
    if end > (x_end + 0xFFF) & ~0xFFF:
        raise SystemExit("sem espaço livre no fim do segmento de código")
    raw = start + (cave - x_va)
    if any(nro[start + (x_end - x_va):raw + len(blob)]):
        raise SystemExit("espaço depois do segmento não está zerado; versão não suportada")

    state = (rw_va + rw_memsz + 15) & ~15
    if state + STATE_SIZE > (rw_va + rw_memsz + 0xFFF) & ~0xFFF:
        raise SystemExit("sem espaço no fim do .bss")

    struct.pack_into("<8I", blob, 0, va, nx_log, callee, dvar_find, state,
                     djb2("r_vsync"), djb2("com_maxfps"), cave)
    nro[raw:raw + len(blob)] = blob
    struct.pack_into("<II", nro, ph_x + 16, end - x_va, end - x_va)
    struct.pack_into("<I", nro, ph_rw + 20, state + STATE_SIZE - rw_va)
    g.put(call_off, enc_bl(call_pc, cave + ENTRY))

    write_nro(nro, src, dst, [
        f"log de desempenho em 0x{cave:x} (estado 0x{state:x}), chamado de 0x{call_pc:x};"
        f" va 0x{va:x}, nx_log 0x{nx_log:x}, Dvar_GetInt 0x{callee:x}, Dvar_FindVarByHash 0x{dvar_find:x}",
    ])


if __name__ == "__main__":
    main()
