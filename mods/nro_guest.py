"""Access to the t6*_guest.elf (ELF32 AArch64 ILP32) embedded in the romfs of a Requiem NX NRO."""
import os
import shutil
import struct


def romfs_file(nro, name):
    """NRO offset and size of file `name` in the romfs root."""
    if nro[0x10:0x14] != b"NRO0":
        raise SystemExit("not an NRO")
    aset = struct.unpack_from("<I", nro, 0x18)[0]
    if nro[aset:aset + 4] != b"ASET":
        raise SystemExit("NRO has no ASET/romfs section")
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
    raise SystemExit(f"{name} not found in romfs")


def find_guest(nro):
    """(name, offset) of the first t6*_guest.elf in the romfs."""
    for name in ("t6mp_guest.elf", "t6zm_guest.elf"):
        try:
            return name, romfs_file(nro, name)[0]
        except SystemExit:
            continue
    raise SystemExit("no t6*_guest.elf in romfs")


class Guest:
    """Returned offsets are NRO offsets; addresses are guest VAs."""

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
        phoff, = struct.unpack_from("<I", nro, start + 0x1C)
        phentsize, phnum = struct.unpack_from("<HH", nro, start + 0x2A)
        self.phdrs = [start + phoff + i * phentsize for i in range(phnum)]

    def word(self, off):
        return struct.unpack_from("<I", self.nro, off)[0]

    def put(self, off, value):
        struct.pack_into("<I", self.nro, off, value)

    def text_words(self):
        addr, off, size = self.secs[".text"]
        return [(addr + i, self.start + off + i) for i in range(0, size, 4)]

    def va_to_off(self, va):
        """NRO offset of a VA backed by file data (PT_LOAD segments)."""
        for ph in self.phdrs:
            ptype, off, vaddr, _, filesz, _, _, _ = struct.unpack_from("<8I", self.nro, ph)
            if ptype == 1 and vaddr <= va < vaddr + filesz:
                return self.start + off + (va - vaddr)
        raise SystemExit(f"VA 0x{va:x} outside the file-backed segments")

    def rodata_strings(self, s):
        """Addresses of every copy of the string (rodata has duplicates)."""
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
            raise SystemExit(f"string {s!r} not found; unsupported version")
        return out

    def _load(self, index):
        """(phdr offset, p_offset, p_vaddr, p_filesz, p_memsz, p_flags) of the index-th PT_LOAD."""
        loads = [p for p in self.phdrs if struct.unpack_from("<I", self.nro, p)[0] == 1]
        _, off, vaddr, _, filesz, memsz, flags, _ = struct.unpack_from("<8I", self.nro, loads[index])
        return loads[index], off, vaddr, filesz, memsz, flags

    def next_code_va(self, align):
        """VA where append_code(..., align) will put the next blob."""
        _, _, vaddr, filesz, _, _ = self._load(0)
        return (vaddr + filesz + align - 1) & ~(align - 1)

    def append_code(self, blob, align):
        """Copies `blob` to the free space after the first PT_LOAD (R+X, text + rodata +
        eh_frame), up to the next page, and grows the segment to cover it. Returns its VA."""
        ph, off, vaddr, filesz, memsz, flags = self._load(0)
        if not flags & 1 or off != 0 or filesz != memsz:
            raise SystemExit("unexpected first guest segment; unsupported version")
        seg_end = vaddr + filesz
        cave = self.next_code_va(align)
        end = cave + len(blob)
        if end > (seg_end + 0xFFF) & ~0xFFF:
            raise SystemExit("no free space at the end of the code segment")
        raw = self.start + off + (cave - vaddr)
        if any(self.nro[self.start + off + filesz:raw + len(blob)]):
            raise SystemExit("space after the code segment is not zeroed; unsupported version")
        self.nro[raw:raw + len(blob)] = blob
        struct.pack_into("<II", self.nro, ph + 16, end - vaddr, end - vaddr)
        return cave

    def alloc_bss(self, size):
        """Grows the RW PT_LOAD by `size` zeroed bytes (16-aligned, same page). Returns their VA."""
        ph, _, vaddr, _, memsz, flags = self._load(1)
        if not flags & 2:
            raise SystemExit("unexpected guest data segment; unsupported version")
        state = (vaddr + memsz + 15) & ~15
        if state + size > (vaddr + memsz + 0xFFF) & ~0xFFF:
            raise SystemExit("no space at the end of .bss")
        struct.pack_into("<I", self.nro, ph + 20, state + size - vaddr)
        return state


def djb2(name):
    """Dvar name hash (lowercase djb2, same as gsc-tool's #"...")."""
    h = 5381
    for c in name.lower().encode():
        h = (c + 33 * h) & 0xFFFFFFFF
    return h


def string_ref(g, words, s):
    """Indexes in `words` of the `add w0, wN, #lo` that form the address of string `s` (with the adrp before)."""
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
    """The next `count` calls after words[j], as (index, target)."""
    out = []
    for m in range(j + 1, min(j + limit, len(words))):
        t = bl_target(words[m][0], g.word(words[m][1]))
        if t is not None:
            out.append((m, t))
            if len(out) == count:
                return out
    raise SystemExit("expected calls not found; unsupported version")


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


def b_target(pc, ins):
    """Target of an unconditional `b`, or None."""
    if (ins & 0xFC000000) != 0x14000000:
        return None
    imm = ins & 0x3FFFFFF
    if imm & (1 << 25):
        imm -= 1 << 26
    return pc + imm * 4


def adrp_target(pc, ins):
    """Target page of an `adrp`, or None if `ins` is not an adrp."""
    if (ins & 0x9F000000) != 0x90000000:
        return None
    imm = (((ins >> 5) & 0x7FFFF) << 2) | ((ins >> 29) & 3)
    if imm & (1 << 20):
        imm -= 1 << 21
    return (pc & ~0xFFF) + (imm << 12)


def bl_target(pc, ins):
    if (ins & 0xFC000000) != 0x94000000:
        return None
    imm = ins & 0x3FFFFFF
    if imm & (1 << 25):
        imm -= 1 << 26
    return pc + imm * 4


def enc_adrp(rd, pc, target):
    imm = (((target & ~0xFFF) - (pc & ~0xFFF)) >> 12) & ((1 << 21) - 1)
    return 0x90000000 | ((imm & 3) << 29) | ((imm >> 2) << 5) | rd


def enc_add_w(rd, rn, imm12):
    return 0x11000000 | (imm12 << 10) | (rn << 5) | rd


def enc_bl(pc, target):
    return 0x94000000 | (((target - pc) >> 2) & 0x3FFFFFF)


def enc_b(pc, target):
    return 0x14000000 | (((target - pc) >> 2) & 0x3FFFFFF)


def enc_bcond(pc, target, cond):
    return 0x54000000 | ((((target - pc) >> 2) & 0x7FFFF) << 5) | cond


def write_nro(nro, src, dst, changes):
    if not changes:
        print("already patched; nothing to do")
        return
    if dst == src and not os.path.exists(src + ".bak"):
        # the first .bak stays the original, even when several patches run in sequence
        shutil.copyfile(src, src + ".bak")
    with open(dst, "wb") as f:
        f.write(nro)
    print("\n".join(changes))
    print(f"-> {dst}")
