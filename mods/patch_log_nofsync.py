#!/usr/bin/env python3
"""t6mp.log / t6zm.log lines without an fsync each (host code, t6mp.nro and t6zm.nro).

The host's log function (vsnprintf + "\\n", write, fsync) calls fsync after every
line, which costs ~17 ms on the SD card and turns every line logged during gameplay
into a visible hitch. The patch replaces that `bl fsync` with a `nop`: lines still
go to the file with write(), only the forced flush is gone.

The crash handler ([nx-crash] lines) has its own fsync on the same file descriptor
after the stack dump and is left untouched, so a crash still flushes everything
logged before it. What can be lost is the last lines if the console powers off or
the SD card is pulled while the game runs.

Usage: python3 patch_log_nofsync.py path/to/t6mp.nro|t6zm.nro [output.nro]
Without [output.nro], overwrites in place and keeps a .bak of the original.
"""
import struct
import sys

from nro_guest import bl_target, write_nro

NOP = 0xD503201F
LDR_FD = 0xB9403460                       # ldr w0, [x3, #0x34]   (log file descriptor)
EPILOGUE = (0xA9407BFD, 0x911443FF, 0xD65F03C0)  # ldp x29, x30, [sp]; add sp, sp, #0x510; ret


def find_fsync_call(nro):
    """NRO offsets of the original `bl fsync` in the log function, and of an already applied nop."""
    text_off, text_size = struct.unpack_from("<II", nro, 0x20)
    n = text_size // 4
    words = struct.unpack_from(f"<{n}I", nro, text_off)
    hits, patched = [], []
    for k in range(2, n - 3):
        if words[k - 1] != LDR_FD or words[k + 1:k + 4] != EPILOGUE:
            continue
        if (words[k - 2] & 0x9F00001F) != 0x90000003:  # adrp x3, <log state>
            continue
        pc = text_off + k * 4
        if words[k] == NOP:
            patched.append(pc)
        elif bl_target(pc, words[k]) is not None:
            hits.append(pc)
    return hits, patched


def main():
    if len(sys.argv) not in (2, 3):
        raise SystemExit(__doc__)
    src = sys.argv[1]
    dst = sys.argv[2] if len(sys.argv) == 3 else src
    nro = bytearray(open(src, "rb").read())
    if nro[0x10:0x14] != b"NRO0":
        raise SystemExit("not an NRO")

    hits, patched = find_fsync_call(nro)
    changes = []
    if len(patched) == 1 and not hits:
        pass
    elif len(hits) == 1 and not patched:
        struct.pack_into("<I", nro, hits[0], NOP)
        changes.append(f"host: log lines without fsync (bl at +0x{hits[0]:x} -> nop)")
    else:
        raise SystemExit(f"log fsync call found {len(hits)} times ({len(patched)} patched); unsupported version")
    write_nro(nro, src, dst, changes)


if __name__ == "__main__":
    main()
