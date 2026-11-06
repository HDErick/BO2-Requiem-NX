#!/usr/bin/env python3
"""Automatic performance log in t6mp.log (multiplayer only).

Hooks perf_log/perf_log.bin (source in perf_log/perf_log.c) into the call the port's
SCR makes once per frame to read cg_drawFPS. t6mp.log then receives:

  [perf] t=123456 ms: 597 frames, avg 16.77 ms, max 60.0 ms, >=20ms 1, >=34ms 1,
         >=50ms 1, >=100ms 0, vsync 1, maxfps 60, log 850 us     (every 10 s)
  [perf] hitch 60 ms at t=123000 ms   (frames >= 50 ms, up to 4 per window)

"t" uses the same clock as the port's own "[load] %u ms" lines, so events can be correlated.
"log" is the worst time spent writing to the log in the previous window; that time is
excluded from the measurements.

The code goes in the free space after the first PT_LOAD (like patch_fps_counter.py);
the state (64 bytes) goes right after .bss, with p_memsz increased. t6zm.nro has no
space left after the FPS counter, so the script refuses it.

Also shortens the host stall watchdog (the thread that writes "[nx-stall]"): instead of
waking every 5 s and only reporting frames stuck for 10 s or more, it wakes every 0.5 s
and reports from 1 s, with the pc/lr and stack of the game's main thread. This shows
where the game is stuck during multi-second stalls (menus, class changes).

Usage: python3 patch_perf_log.py path/to/t6mp.nro [output.nro]
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


# host watchdog: 5 s wait (0x12A05F200 ns) between checks ...
WATCH_WAIT = (0xD29E4003, 0xF2A540A3, 0xB90053F5, 0xF2C00023)  # mov/movk x3; str w21,[sp,#0x50]; movk x3
WATCH_WAIT_NEW = (0xD28CA003, 0xF2A3B9A3, 0xB90053F5, 0xF2C00003)  # 500 000 000 ns
# ... and "seconds without a frame > 9" before reporting
WATCH_LIMIT = (0xD358FC21, 0x2A0103E0, 0x7100243F)             # lsr x1,x1,#24; mov w0,w1; cmp w1,#9
WATCH_LIMIT_NEW = (0xD358FC21, 0x2A0103E0, 0x7100003F)          # cmp w1, #0  -> from 1 s


def patch_watchdog(nro):
    """Shortens the host stall watchdog (NRO code, outside the guest)."""
    text_off, text_size = struct.unpack_from("<II", nro, 0x20)
    text = nro[text_off:text_off + text_size]
    changes = []
    for old, new, what in ((WATCH_WAIT, WATCH_WAIT_NEW, "watchdog wakes every 0.5 s"),
                           (WATCH_LIMIT, WATCH_LIMIT_NEW, "stalls reported from 1 s")):
        old_b, new_b = struct.pack(f"<{len(old)}I", *old), struct.pack(f"<{len(new)}I", *new)
        hits, done = text.count(old_b), text.count(new_b)
        if done == 1 and hits == 0:
            continue
        if hits != 1:
            raise SystemExit(f"host stall watchdog: signature found {hits} times; unsupported version")
        pos = text_off + text.find(old_b)
        nro[pos:pos + len(new_b)] = new_b
        changes.append(f"host: {what} (+0x{pos:x})")
    return changes


def string_ref(g, words, s):
    """Offsets of the `add w0, wN, #lo` that form the address of string `s` (with the adrp before)."""
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
    raise SystemExit("expected calls not found; unsupported version")


def find_log_fns(g, words):
    """va() and nx_log() from nx_log(va("[load] %u ms: zone %s done, %d assets", ...))."""
    refs = string_ref(g, words, "[load] %u ms: zone %s done, %d assets")
    if len(refs) != 1:
        raise SystemExit("port [load] line not found; unsupported version")
    (m1, va), (m2, nx_log) = next_bls(g, words, refs[0], 2, limit=6)
    if m2 != m1 + 1:
        raise SystemExit("unexpected log call; unsupported version")
    return va, nx_log


def find_dvar_find(g, words):
    """Dvar_FindVarByHash: in SetSavedDvar, `bl hash; bl find; mov w1, w0; cbz w0, ...`."""
    found = set()
    for j in string_ref(g, words, 'SetSavedDvar(): The dvar "%s" does not exist.'):
        for m in range(max(j - 200, 0), min(j + 200, len(words) - 3)):
            a, b = g.word(words[m][1]), g.word(words[m + 1][1])
            if bl_target(words[m][0], a) and bl_target(words[m + 1][0], b) \
                    and g.word(words[m + 2][1]) == 0x2A0003E1 \
                    and (g.word(words[m + 3][1]) & 0xFF00001F) == 0x34000000:
                found.add(bl_target(words[m + 1][0], b))
    if len(found) != 1:
        raise SystemExit(f"Dvar_FindVarByHash found {len(found)} times; unsupported version")
    return found.pop()


def find_hook(g, words):
    """(offset of the bl, VA of the bl, current target) of Dvar_GetInt(cg_drawFPS) in the port's SCR."""
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
        raise SystemExit("dvar cg_drawFPS not found; unsupported version")
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
        raise SystemExit(f"per-frame cg_drawFPS read found {len(sites)} times; unsupported version")
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
        raise SystemExit("unexpected guest segments; unsupported version")

    changes = patch_watchdog(nro)

    call_off, call_pc, callee = find_hook(g, words)
    x_end = x_va + x_filesz
    if callee < g.secs[".eh_frame"][0] + g.secs[".eh_frame"][2]:
        va, nx_log = find_log_fns(g, words)
        dvar_find = find_dvar_find(g, words)

        blob = bytearray(open(BLOB, "rb").read())
        cave = (x_end + 15) & ~15
        end = cave + len(blob)
        if end > (x_end + 0xFFF) & ~0xFFF:
            raise SystemExit("no free space at the end of the code segment")
        raw = start + (cave - x_va)
        if any(nro[start + (x_end - x_va):raw + len(blob)]):
            raise SystemExit("space after the segment is not zeroed; unsupported version")

        state = (rw_va + rw_memsz + 15) & ~15
        if state + STATE_SIZE > (rw_va + rw_memsz + 0xFFF) & ~0xFFF:
            raise SystemExit("no space at the end of .bss")

        struct.pack_into("<8I", blob, 0, va, nx_log, callee, dvar_find, state,
                         djb2("r_vsync"), djb2("com_maxfps"), cave)
        nro[raw:raw + len(blob)] = blob
        struct.pack_into("<II", nro, ph_x + 16, end - x_va, end - x_va)
        struct.pack_into("<I", nro, ph_rw + 20, state + STATE_SIZE - rw_va)
        g.put(call_off, enc_bl(call_pc, cave + ENTRY))
        changes.append(
            f"performance log at 0x{cave:x} (state 0x{state:x}), called from 0x{call_pc:x};"
            f" va 0x{va:x}, nx_log 0x{nx_log:x}, Dvar_GetInt 0x{callee:x}, Dvar_FindVarByHash 0x{dvar_find:x}")

    write_nro(nro, src, dst, changes)


if __name__ == "__main__":
    main()
