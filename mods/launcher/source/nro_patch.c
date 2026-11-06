#include "nro_patch.h"

#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef uint32_t u32;

/* ------------------------------------------------------------------ errors */

typedef struct {
    char *err;
    size_t errlen;
} Ctx;

static int fail(Ctx *c, const char *fmt, ...)
{
    if (c->err && c->errlen) {
        va_list ap;
        va_start(ap, fmt);
        vsnprintf(c->err, c->errlen, fmt, ap);
        va_end(ap);
    }
    return -1;
}

#define TRY(x) do { if ((x) < 0) return -1; } while (0)

/* ------------------------------------------------------------------ bytes */

static u32 rd32(const uint8_t *p) { return p[0] | p[1] << 8 | p[2] << 16 | (u32)p[3] << 24; }
static void wr32(uint8_t *p, u32 v) { p[0] = v; p[1] = v >> 8; p[2] = v >> 16; p[3] = v >> 24; }
static uint64_t rd64(const uint8_t *p) { return rd32(p) | (uint64_t)rd32(p + 4) << 32; }
static unsigned rd16(const uint8_t *p) { return p[0] | p[1] << 8; }

/* ------------------------------------------------------------------ instructions */

#define NONE 0xFFFFFFFFu   /* "not this instruction" (no valid target is 0xFFFFFFFF) */
#define NOP 0xD503201Fu

static u32 adrp_target(u32 pc, u32 ins)
{
    if ((ins & 0x9F000000) != 0x90000000)
        return NONE;
    int32_t imm = (int32_t)((((ins >> 5) & 0x7FFFF) << 2) | ((ins >> 29) & 3));
    if (imm & (1 << 20))
        imm -= 1 << 21;
    return (pc & ~0xFFFu) + (u32)(imm << 12);
}

static u32 imm26_target(u32 pc, u32 ins)
{
    int32_t imm = ins & 0x3FFFFFF;
    if (imm & (1 << 25))
        imm -= 1 << 26;
    return pc + (u32)(imm * 4);
}

static u32 bl_target(u32 pc, u32 ins) { return (ins & 0xFC000000) == 0x94000000 ? imm26_target(pc, ins) : NONE; }
static u32 b_target(u32 pc, u32 ins) { return (ins & 0xFC000000) == 0x14000000 ? imm26_target(pc, ins) : NONE; }

static u32 tb_target(u32 pc, u32 ins)
{
    int32_t imm = (ins >> 5) & 0x3FFF;
    if (imm & (1 << 13))
        imm -= 1 << 14;
    return pc + (u32)(imm * 4);
}

static u32 enc_adrp(u32 rd, u32 pc, u32 target)
{
    u32 imm = (((target & ~0xFFFu) - (pc & ~0xFFFu)) >> 12) & ((1u << 21) - 1);
    return 0x90000000 | (imm & 3) << 29 | (imm >> 2) << 5 | rd;
}

static u32 enc_add_w(u32 rd, u32 rn, u32 imm12) { return 0x11000000 | imm12 << 10 | rn << 5 | rd; }
static u32 enc_bl(u32 pc, u32 target) { return 0x94000000 | (((target - pc) >> 2) & 0x3FFFFFF); }
static u32 enc_b(u32 pc, u32 target) { return 0x14000000 | (((target - pc) >> 2) & 0x3FFFFFF); }
static u32 enc_bcond(u32 pc, u32 target, u32 cond) { return 0x54000000 | (((target - pc) >> 2) & 0x7FFFF) << 5 | cond; }

/* ------------------------------------------------------------------ NRO / romfs */

static int in_range(size_t size, uint64_t off, uint64_t len) { return off <= size && len <= size - off; }

/* NRO offset of the romfs root file `name`; -1 if missing */
static int romfs_file(Ctx *c, const uint8_t *nro, size_t size, const char *name, size_t *out)
{
    if (size < 0x80 || memcmp(nro + 0x10, "NRO0", 4))
        return fail(c, "not an NRO");
    u32 aset = rd32(nro + 0x18);
    if (!in_range(size, aset, 0x48) || memcmp(nro + aset, "ASET", 4))
        return fail(c, "NRO has no ASET/romfs section");
    uint64_t rom = aset + rd64(nro + aset + 8 + 32);
    if (!in_range(size, rom, 0x50))
        return -1;
    uint64_t fm_off = rd64(nro + rom + 56), fm_size = rd64(nro + rom + 64), data_off = rd64(nro + rom + 72);
    size_t nl = strlen(name);
    for (uint64_t pos = 0; pos < fm_size;) {
        const uint8_t *e = nro + rom + fm_off + pos;
        if (!in_range(size, rom + fm_off + pos, 32))
            break;
        uint64_t foff = rd64(e + 8);
        u32 len = rd32(e + 28);
        if (len == nl && in_range(size, rom + fm_off + pos + 32, len) && !memcmp(e + 32, name, nl)) {
            *out = rom + data_off + foff;
            return 0;
        }
        pos += 32 + ((len + 3) & ~3u);
    }
    return -1;
}

/* ------------------------------------------------------------------ guest ELF */

typedef struct { u32 addr, off, size; } Sec;

typedef struct {
    uint8_t *nro;
    size_t size;
    size_t start;           /* NRO offset of the ELF */
    int is_mp;
    Sec text, rodata, eh_frame;
    size_t ph_load[2];      /* NRO offsets of the first two PT_LOAD headers */
    u32 n;                  /* .text words */
} Guest;

static u32 gword(const Guest *g, size_t off) { return rd32(g->nro + off); }
static void gput(Guest *g, size_t off, u32 v) { wr32(g->nro + off, v); }
static u32 tpc(const Guest *g, u32 i) { return g->text.addr + 4 * i; }
static size_t toff(const Guest *g, u32 i) { return g->start + g->text.off + 4 * (size_t)i; }
static u32 tw(const Guest *g, u32 i) { return gword(g, toff(g, i)); }
static u32 code_end(const Guest *g) { return g->eh_frame.addr + g->eh_frame.size; }

static int guest_open(Ctx *c, Guest *g, uint8_t *nro, size_t size)
{
    memset(g, 0, sizeof *g);
    g->nro = nro;
    g->size = size;
    if (romfs_file(c, nro, size, "t6mp_guest.elf", &g->start) == 0)
        g->is_mp = 1;
    else if (romfs_file(c, nro, size, "t6zm_guest.elf", &g->start))
        return fail(c, "no t6*_guest.elf in romfs");
    size_t s = g->start;
    if (!in_range(size, s, 0x34) || memcmp(nro + s, "\x7f" "ELF", 4))
        return fail(c, "guest is not an ELF");
    u32 shoff = rd32(nro + s + 0x20), phoff = rd32(nro + s + 0x1C);
    unsigned phentsize = rd16(nro + s + 0x2A), phnum = rd16(nro + s + 0x2C);
    unsigned shentsize = rd16(nro + s + 0x2E), shnum = rd16(nro + s + 0x30), shstrndx = rd16(nro + s + 0x32);
    if (!in_range(size, s + shoff, (uint64_t)shentsize * shnum) || shstrndx >= shnum ||
        !in_range(size, s + phoff, (uint64_t)phentsize * phnum))
        return fail(c, "bad guest headers");
    size_t strtab = s + rd32(nro + s + shoff + shstrndx * shentsize + 16);
    for (unsigned i = 0; i < shnum; i++) {
        const uint8_t *sh = nro + s + shoff + i * shentsize;
        const char *name = (const char *)nro + strtab + rd32(sh);
        Sec sec = {rd32(sh + 12), rd32(sh + 16), rd32(sh + 20)};
        if (!strcmp(name, ".text"))
            g->text = sec;
        else if (!strcmp(name, ".rodata"))
            g->rodata = sec;
        else if (!strcmp(name, ".eh_frame"))
            g->eh_frame = sec;
    }
    int loads = 0;
    for (unsigned i = 0; i < phnum && loads < 2; i++) {
        size_t ph = s + phoff + i * phentsize;
        if (rd32(nro + ph) == 1)
            g->ph_load[loads++] = ph;
    }
    if (!g->text.size || !g->rodata.size || !g->eh_frame.size || loads < 2 ||
        !in_range(size, s + g->text.off, g->text.size) || !in_range(size, s + g->rodata.off, g->rodata.size))
        return fail(c, "unexpected guest layout; unsupported version");
    g->n = g->text.size / 4;
    return 0;
}

#define MAX_STR 128

/* VAs of every copy of string s in .rodata */
static int rodata_strings(Ctx *c, const Guest *g, const char *s, u32 *out)
{
    size_t lo = g->start + g->rodata.off, hi = lo + g->rodata.size, sl = strlen(s);
    int n = 0;
    for (size_t p = lo; p + sl + 2 <= hi && n < MAX_STR; p++) {
        if (g->nro[p] || g->nro[p + 1] != (uint8_t)s[0] || memcmp(g->nro + p + 1, s, sl) || g->nro[p + 1 + sl])
            continue;
        out[n++] = g->rodata.addr + (u32)(p + 1 - lo);
    }
    if (!n)
        return fail(c, "string '%s' not found; unsupported version", s);
    return n;
}

static int contains(const u32 *v, int n, u32 x)
{
    for (int i = 0; i < n; i++)
        if (v[i] == x)
            return 1;
    return 0;
}

/* .text indexes of the `add w0, wN, #lo` that form the address of string s (with the adrp before) */
static int string_ref(Ctx *c, const Guest *g, const char *s, u32 *hits, int max)
{
    u32 targets[MAX_STR];
    int nt = rodata_strings(c, g, s, targets), nh = 0;
    TRY(nt);
    for (u32 k = 0; k + 1 < g->n; k++) {
        u32 ins = tw(g, k), page = adrp_target(tpc(g, k), ins);
        if (page == NONE)
            continue;
        u32 rd = ins & 31;
        for (u32 j = k + 1; j < k + 12 && j < g->n; j++) {
            u32 a = tw(g, j);
            if ((a & 0xFFC0001F) == 0x11000000 && ((a >> 5) & 31) == rd &&
                contains(targets, nt, page + ((a >> 10) & 0xFFF))) {
                if (nh < max)
                    hits[nh] = j;
                nh++;
                break;
            }
        }
    }
    return nh;
}

/* the next `count` calls after index j: (index, target) */
static int next_bls(Ctx *c, const Guest *g, u32 j, int count, u32 limit, u32 *idx, u32 *target)
{
    int got = 0;
    for (u32 m = j + 1; m < j + limit && m < g->n; m++) {
        u32 t = bl_target(tpc(g, m), tw(g, m));
        if (t != NONE) {
            idx[got] = m;
            target[got] = t;
            if (++got == count)
                return 0;
        }
    }
    return fail(c, "expected calls not found; unsupported version");
}

static u32 djb2(const char *s)
{
    u32 h = 5381;
    for (; *s; s++) {
        unsigned ch = (unsigned char)*s;
        if (ch >= 'A' && ch <= 'Z')
            ch += 32;
        h = ch + 33 * h;
    }
    return h;
}

/* Dvar_FindVarByHash: in SetSavedDvar, `bl hash; bl find; mov w1, w0; cbz w0, ...` */
static int find_dvar_find(Ctx *c, const Guest *g, u32 *out)
{
    u32 refs[16];
    int nr = string_ref(c, g, "SetSavedDvar(): The dvar \"%s\" does not exist.", refs, 16);
    TRY(nr);
    u32 found = NONE;
    for (int r = 0; r < nr && r < 16; r++) {
        u32 j = refs[r];
        u32 m0 = j > 200 ? j - 200 : 0, m1 = j + 200 < g->n - 3 ? j + 200 : g->n - 3;
        for (u32 m = m0; m < m1; m++) {
            u32 a = bl_target(tpc(g, m), tw(g, m)), b = bl_target(tpc(g, m + 1), tw(g, m + 1));
            if (a != NONE && a && b != NONE && b && tw(g, m + 2) == 0x2A0003E1 &&
                (tw(g, m + 3) & 0xFF00001F) == 0x34000000) {
                if (found != NONE && found != b)
                    return fail(c, "Dvar_FindVarByHash found more than once; unsupported version");
                found = b;
            }
        }
    }
    if (found == NONE)
        return fail(c, "Dvar_FindVarByHash not found; unsupported version");
    *out = found;
    return 0;
}

/* ------------------------------------------------------------------ segments */

static u32 next_code_va(const Guest *g, u32 align)
{
    const uint8_t *ph = g->nro + g->ph_load[0];
    return (rd32(ph + 8) + rd32(ph + 16) + align - 1) & ~(align - 1);
}

static int append_code(Ctx *c, Guest *g, const uint8_t *blob, size_t len, u32 align, u32 *out)
{
    uint8_t *ph = g->nro + g->ph_load[0];
    u32 off = rd32(ph + 4), va = rd32(ph + 8), filesz = rd32(ph + 16), memsz = rd32(ph + 20), flags = rd32(ph + 24);
    if (!(flags & 1) || off != 0 || filesz != memsz)
        return fail(c, "unexpected first guest segment; unsupported version");
    u32 seg_end = va + filesz, cave = next_code_va(g, align), end = cave + (u32)len;
    if (end > ((seg_end + 0xFFF) & ~0xFFFu))
        return fail(c, "no free space at the end of the code segment");
    size_t raw = g->start + off + (cave - va);
    if (!in_range(g->size, raw, len))
        return fail(c, "code segment outside the file");
    for (size_t p = g->start + off + filesz; p < raw + len; p++)
        if (g->nro[p])
            return fail(c, "space after the code segment is not zeroed; unsupported version");
    memcpy(g->nro + raw, blob, len);
    wr32(ph + 16, end - va);
    wr32(ph + 20, end - va);
    *out = cave;
    return 0;
}

static int alloc_bss(Ctx *c, Guest *g, u32 size, u32 *out)
{
    uint8_t *ph = g->nro + g->ph_load[1];
    u32 va = rd32(ph + 8), memsz = rd32(ph + 20), flags = rd32(ph + 24);
    if (!(flags & 2))
        return fail(c, "unexpected guest data segment; unsupported version");
    u32 state = (va + memsz + 15) & ~15u;
    if (state + size > ((va + memsz + 0xFFF) & ~0xFFFu))
        return fail(c, "no space at the end of .bss");
    wr32(ph + 20, state + size - va);
    *out = state;
    return 0;
}

/* ------------------------------------------------------------------ aim assist (patch_mp_aimassist.py) */

#define MOV_W1_0 0x52800001u
#define MOV_W1_1 0x52800021u
#define GATE_ALLOW 0x18
#define GATE_DENY 0x1C
#define GATE_ENTRY 0x20
#define GATE_STATE 8

enum { GATE_STOCK, GATE_NOP, GATE_GATE };

typedef struct { size_t off; u32 pc, exit_va; int state; } GateSite;

static int find_gate(Ctx *c, const Guest *g, GateSite *out)
{
    int n = 0;
    for (u32 i = 4; i + 3 < g->n; i++) {
        if (!(tw(g, i - 4) == 0x39400860 &&                 /* ldrb w0, [x3, #2] */
              (tw(g, i - 3) & 0xFFF8001F) == 0x37000000 &&  /* tbnz w0, #0, ... */
              tw(g, i + 1) == 0xB9402483 &&                 /* ldr  w3, [x4, #0x24] */
              (tw(g, i + 2) & 0xFFF8001F) == 0x36A00003))   /* tbz  w3, #0x14, <exit> */
            continue;
        u32 pc = tpc(g, i), w = tw(g, i), exit_va = tb_target(pc + 8, tw(g, i + 2));
        int state;
        if ((w & 0xFFF8001F) == 0x36200003 && tb_target(pc, w) == exit_va)
            state = GATE_STOCK;
        else if (w == NOP)
            state = GATE_NOP;
        else if (b_target(pc, w) != NONE && b_target(pc, w) >= code_end(g))
            state = GATE_GATE;
        else
            continue;
        *out = (GateSite){toff(g, i), pc, exit_va, state};
        n++;
    }
    if (n != 1)
        return fail(c, "auto-aim signature found %d times (expected 1); unsupported version", n);
    return 0;
}

static const u32 DVAR_INT_SIG[][2] = {{0, 0x2A0003E1}, {2, 0xB9401020}, {3, 0x51001802}, {4, 0x7100045F},
                                      {6, 0x7100041F}, {8, 0x7100081F}, {10, 0xB9401820}, {12, 0xB9401820},
                                      {13, 0xD65F03C0}};

static int match_sig(const Guest *g, u32 i, const u32 (*sig)[2], int n)
{
    for (int k = 0; k < n; k++)
        if (tw(g, i + sig[k][0]) != sig[k][1])
            return 0;
    return 1;
}

static int find_dvar_int(Ctx *c, const Guest *g, u32 *out)
{
    int n = 0;
    for (u32 i = 0; i + 14 < g->n; i++)
        if (match_sig(g, i, DVAR_INT_SIG, 9)) {
            *out = tpc(g, i);
            n++;
        }
    if (n != 1)
        return fail(c, "Dvar_GetInt found %d times; unsupported version", n);
    return 0;
}

/* offset of the `mov w1, #default` in the call that registers dvar `name` */
static int find_bool_default(Ctx *c, const Guest *g, const char *name, size_t *out)
{
    u32 targets[MAX_STR];
    int nt = rodata_strings(c, g, name, targets), ns = 0;
    TRY(nt);
    size_t site = 0;
    for (u32 k = 0; k < g->n; k++) {
        u32 ins = tw(g, k), page = adrp_target(tpc(g, k), ins);
        if (page == NONE)
            continue;
        u32 rd = ins & 31;
        for (u32 j = k + 1; j < k + 12 && j < g->n; j++) {
            u32 a = tw(g, j);
            if ((a & 0xFFC003FF) != (0x11000000 | rd << 5) || !contains(targets, nt, page + ((a >> 10) & 0xFFF)))
                continue;
            u32 call = NONE;
            for (u32 m = j + 1; m < j + 40 && m < g->n; m++)
                if (bl_target(tpc(g, m), tw(g, m)) != NONE) {
                    call = m;
                    break;
                }
            if (call == NONE)
                break;
            /* the mov w1 may come before or after the name add; the last one before the bl wins */
            u32 stop = call > 60 ? call - 60 : 0;
            for (u32 m = call - 1; m > stop; m--) {
                if (bl_target(tpc(g, m), tw(g, m)) != NONE)
                    break;
                if (tw(g, m) == MOV_W1_0 || tw(g, m) == MOV_W1_1) {
                    if (!ns || site != toff(g, m))
                        ns++;
                    site = toff(g, m);
                    break;
                }
            }
            break;
        }
    }
    if (ns != 1)
        return fail(c, "registration of %s found %d times; unsupported version", name, ns);
    *out = site;
    return 0;
}

static const u32 RANGE_SIG[][2] = {{0, 0xBD45705F}, {3, 0x1E3F0800}, {5, 0x1E2023E0},
                                   {6, 0x54000121}, {32, 0x52A8B000}, {33, 0x1E270000}};

static int find_range(Ctx *c, const Guest *g, size_t *out)
{
    int n = 0;
    for (u32 i = 0; i + 40 < g->n; i++)
        if (match_sig(g, i, RANGE_SIG, 6)) {
            *out = toff(g, i);
            n++;
        }
    if (n != 1)
        return fail(c, "AimAssist_GetAutoAimRange found %d times; unsupported version", n);
    return 0;
}

static int aim_detect(Ctx *c, const Guest *g, int *state)
{
    GateSite s;
    TRY(find_gate(c, g, &s));
    *state = s.state == GATE_STOCK ? MOD_OFF : MOD_ON;
    return 0;
}

static int aim_apply(Ctx *c, Guest *g, const Blob *gate)
{
    GateSite s;
    TRY(find_gate(c, g, &s));
    if (s.state != GATE_GATE) {
        if (!gate->data || gate->size < GATE_ENTRY + 4)
            return fail(c, "aim_gate.bin missing");
        uint8_t *blob = malloc(gate->size);
        if (!blob)
            return fail(c, "out of memory");
        memcpy(blob, gate->data, gate->size);
        u32 cave = next_code_va(g, 16), state, find, get_int, at;
        if (alloc_bss(c, g, GATE_STATE, &state) || find_dvar_find(c, g, &find) || find_dvar_int(c, g, &get_int)) {
            free(blob);
            return -1;
        }
        u32 tbl[6] = {find, get_int, state, djb2("sv_running"), djb2("nx_aimassist_allowed"), cave};
        for (int i = 0; i < 6; i++)
            wr32(blob + 4 * i, tbl[i]);
        wr32(blob + GATE_ALLOW, enc_b(cave + GATE_ALLOW, s.pc + 4));
        wr32(blob + GATE_DENY, enc_b(cave + GATE_DENY, s.exit_va));
        int r = append_code(c, g, blob, gate->size, 16, &at);
        free(blob);
        TRY(r);
        gput(g, s.off, enc_b(s.pc, cave + GATE_ENTRY));
    }

    size_t off;
    TRY(find_bool_default(c, g, "aim_lockon_enabled", &off));
    if (gword(g, off) == MOV_W1_0)
        gput(g, off, MOV_W1_1);

    size_t base;
    TRY(find_range(c, g, &base));
    /* ldr s31, [x0] -> fmov s31, wzr (compare with 0.0); adrp x0, ... -> b +0x64 (straight to 4096.0) */
    static const u32 fix[2][3] = {{4, 0xBD40001F, 0x1E2703FF}, {7, 0x90000000, 0x14000019}};
    for (int i = 0; i < 2; i++) {
        size_t at = base + 4 * fix[i][0];
        u32 cur = gword(g, at);
        if (cur == fix[i][2])
            continue;
        if ((i == 1 ? (cur & 0x9F00001F) : cur) != fix[i][1])
            return fail(c, "AimAssist_GetAutoAimRange differs from expected; unsupported version");
        gput(g, at, fix[i][2]);
    }
    return 0;
}

/* ------------------------------------------------------------------ FPS counter (patch_fps_counter.py) */

#define FSUB_S0 0x1E3E3BE0u   /* fsub s0, s31, s30 */
#define STR_S0 0xBD0073E0u    /* str s0, [sp, #0x70] */
static const char FPS_FMT[] = "%i fps  %i.%i ms  max %i ms";

typedef struct { size_t call_off; u32 call_pc, callee, buf; } FpsSite;

static int fps_find(Ctx *c, const Guest *g, FpsSite *out)
{
    u32 fmts[MAX_STR];
    int nf = rodata_strings(c, g, "%i fps", fmts), n = 0;
    TRY(nf);
    for (u32 i = 0x25; i + 4 < g->n; i++) {
        u32 pc = tpc(g, i), w = tw(g, i), page = adrp_target(pc, w);
        if (page == NONE || (w & 31) != 0)
            continue;
        u32 add = tw(g, i + 1);
        if ((add & 0xFFC003FF) != 0x11000000 || !contains(fmts, nf, page + ((add >> 10) & 0xFFF)))
            continue;
        if (tw(g, i + 2) != FSUB_S0 || tw(g, i + 3) != STR_S0)
            continue;
        u32 call_pc = pc + 16, callee = bl_target(call_pc, tw(g, i + 4));
        /* buffer: adrp x0 / add w0, w0, #lo 0x74 bytes before the format adrp */
        u32 b_adrp = tw(g, i - 0x1D), b_add = tw(g, i - 0x1C), bpage = adrp_target(pc - 0x74, b_adrp);
        if (callee == NONE || bpage == NONE || (b_add & 0xFFC003FF) != 0x11000000)
            continue;
        u32 buf = bpage + ((b_add >> 10) & 0xFFF);
        /* the counter sits 8 bytes before it: str w2, [x4, #(buf-8)&0xfff] */
        if (tw(g, i - 0x25) != (0xB9000082 | (((buf - 8) & 0xFFF) / 4) << 10))
            continue;
        *out = (FpsSite){toff(g, i + 4), call_pc, callee, buf};
        n++;
    }
    if (n != 1)
        return fail(c, "FPS counter found %d times; unsupported version", n);
    return 0;
}

/* see build_cave() in patch_fps_counter.py */
static size_t fps_build(uint8_t *out, u32 cave, u32 va, u32 buf)
{
    u32 code[40];
    int n = 0;
#define PC (cave + 4 * n)
    code[n] = enc_adrp(9, PC, buf - 8); n++;
    code[n++] = 0xB940012A | (((buf - 8) & 0xFFF) / 4) << 10;  /* ldr w10, [x9, #count] */
    code[n++] = 0x5280040B;                                      /* mov w11, #32 */
    code[n++] = 0x7100815F;                                      /* cmp w10, #32 */
    code[n++] = 0x1A8BD14A;                                      /* csel w10, w10, w11, le */
    code[n++] = enc_add_w(9, 9, buf & 0xFFF);
    code[n++] = 0x5280000C;                                      /* mov w12, #0 (sum) */
    code[n++] = 0x5280000D;                                      /* mov w13, #0 (max) */
    code[n++] = 0x5280000E;                                      /* mov w14, #0 (i) */
    u32 loop = PC;
    code[n++] = 0x6B0A01DF;                                      /* cmp w14, w10 */
    int bge = n++;
    code[n++] = 0xB86E592F;                                      /* ldr w15, [x9, w14, uxtw #2] */
    code[n++] = 0x0B0F018C;                                      /* add w12, w12, w15 */
    code[n++] = 0x6B0D01FF;                                      /* cmp w15, w13 */
    code[n++] = 0x1A8DC1ED;                                      /* csel w13, w15, w13, gt */
    code[n++] = 0x110005CE;                                      /* add w14, w14, #1 */
    code[n] = enc_b(PC, loop); n++;
    code[bge] = enc_bcond(loop + 4, PC, 0xA);                    /* b.ge */
    code[n++] = 0x5280014F;                                      /* mov w15, #10 */
    code[n++] = 0x1B0F7D8C;                                      /* mul w12, w12, w15 */
    code[n++] = 0x1ACA098C;                                      /* udiv w12, w12, w10 */
    code[n++] = 0x1ACF0982;                                      /* udiv w2, w12, w15 */
    code[n++] = 0x1B0FB043;                                      /* msub w3, w2, w15, w12 */
    code[n++] = 0x2A0D03E4;                                      /* mov w4, w13 */
    int fmt_at = n;
    n += 2;
    code[n] = enc_b(PC, va); n++;                                /* tail call: va() */
    u32 fmt_va = PC;
    code[fmt_at] = enc_adrp(0, cave + 4 * fmt_at, fmt_va);
    code[fmt_at + 1] = enc_add_w(0, 0, fmt_va & 0xFFF);
#undef PC
    for (int i = 0; i < n; i++)
        wr32(out + 4 * i, code[i]);
    memcpy(out + 4 * n, FPS_FMT, sizeof FPS_FMT);
    return 4 * (size_t)n + sizeof FPS_FMT;
}

static int fps_detect(Ctx *c, const Guest *g, int *state)
{
    FpsSite s;
    TRY(fps_find(c, g, &s));
    *state = s.callee >= code_end(g) ? MOD_ON : MOD_OFF;
    return 0;
}

static int fps_apply(Ctx *c, Guest *g)
{
    FpsSite s;
    TRY(fps_find(c, g, &s));
    if (s.callee >= code_end(g))
        return 0;
    uint8_t blob[256];
    u32 cave = next_code_va(g, 4), at;
    size_t len = fps_build(blob, cave, s.callee, s.buf);
    TRY(append_code(c, g, blob, len, 4, &at));
    gput(g, s.call_off, enc_bl(s.call_pc, cave));
    return 0;
}

/* ------------------------------------------------------------------ host code */

static int host_text(Ctx *c, const uint8_t *nro, size_t size, size_t *off, size_t *len)
{
    if (size < 0x80 || memcmp(nro + 0x10, "NRO0", 4))
        return fail(c, "not an NRO");
    *off = rd32(nro + 0x20);
    *len = rd32(nro + 0x24);
    if (!in_range(size, *off, *len))
        return fail(c, "bad NRO header");
    return 0;
}

static int count_words(const uint8_t *text, size_t len, const u32 *w, int n, size_t *first)
{
    uint8_t pat[32];
    for (int i = 0; i < n; i++)
        wr32(pat + 4 * i, w[i]);
    size_t pl = 4 * (size_t)n;
    int hits = 0;
    for (size_t p = 0; p + pl <= len;) {
        const uint8_t *f = memchr(text + p, pat[0], len - pl + 1 - p);
        if (!f)
            break;
        p = f - text;
        if (!memcmp(text + p, pat, pl)) {
            if (!hits)
                *first = p;
            hits++;
            p += pl;
        } else {
            p++;
        }
    }
    return hits;
}

/* host stall watchdog (patch_watchdog in patch_perf_log.py) */
static const u32 WATCH[2][2][4] = {
    {{0xD29E4003, 0xF2A540A3, 0xB90053F5, 0xF2C00023}, {0xD28CA003, 0xF2A3B9A3, 0xB90053F5, 0xF2C00003}},
    {{0xD358FC21, 0x2A0103E0, 0x7100243F, 0}, {0xD358FC21, 0x2A0103E0, 0x7100003F, 0}},
};
static const int WATCH_LEN[2] = {4, 3};

static int watchdog_apply(Ctx *c, uint8_t *nro, size_t size)
{
    size_t off, len, first = 0, dummy;
    TRY(host_text(c, nro, size, &off, &len));
    for (int i = 0; i < 2; i++) {
        int hits = count_words(nro + off, len, WATCH[i][0], WATCH_LEN[i], &first);
        int done = count_words(nro + off, len, WATCH[i][1], WATCH_LEN[i], &dummy);
        if (done == 1 && hits == 0)
            continue;
        if (hits != 1)
            return fail(c, "host stall watchdog: signature found %d times; unsupported version", hits);
        for (int k = 0; k < WATCH_LEN[i]; k++)
            wr32(nro + off + first + 4 * k, WATCH[i][1][k]);
    }
    return 0;
}

/* log fsync (patch_log_nofsync.py) */
#define LDR_FD 0xB9403460u
static const u32 LOG_EPILOGUE[3] = {0xA9407BFD, 0x911443FF, 0xD65F03C0};

static int nofsync_find(Ctx *c, const uint8_t *nro, size_t size, size_t *site, int *patched)
{
    size_t off, len;
    TRY(host_text(c, nro, size, &off, &len));
    int hits = 0, done = 0;
    for (size_t k = 2; k + 3 < len / 4; k++) {
        const uint8_t *p = nro + off + 4 * k;
        if (rd32(p - 4) != LDR_FD || rd32(p + 4) != LOG_EPILOGUE[0] || rd32(p + 8) != LOG_EPILOGUE[1] ||
            rd32(p + 12) != LOG_EPILOGUE[2] || (rd32(p - 8) & 0x9F00001F) != 0x90000003)
            continue;
        u32 pc = (u32)(off + 4 * k);
        if (rd32(p) == NOP) {
            done++;
            *site = pc;
        } else if (bl_target(pc, rd32(p)) != NONE) {
            hits++;
            *site = pc;
        }
    }
    if (hits + done != 1)
        return fail(c, "log fsync call found %d times (%d patched); unsupported version", hits, done);
    *patched = done;
    return 0;
}

/* ------------------------------------------------------------------ performance log (patch_perf_log.py) */

#define PERF_ENTRY 0x20
#define PERF_STATE 0x40

typedef struct { size_t call_off; u32 call_pc, callee; } HookSite;

/* Dvar_GetInt(cg_drawFPS) read once per frame by the port's SCR */
static int perf_find_hook(Ctx *c, const Guest *g, HookSite *out)
{
    u32 refs[16];
    int nr = string_ref(c, g, "cg_drawFPS", refs, 16);
    TRY(nr);
    u32 gv = NONE;
    int ng = 0;
    for (int r = 0; r < nr && r < 16; r++) {
        u32 m, t;
        TRY(next_bls(c, g, refs[r], 1, 4, &m, &t));
        for (u32 k = m + 1; k < m + 8 && k < g->n; k++) {
            u32 s = tw(g, k);
            if ((s & 0xFFC0001F) != 0xB9000000)   /* str w0, [xN, #imm] */
                continue;
            u32 rn = (s >> 5) & 31;
            for (u32 p = k - 1; p > (k > 8 ? k - 8 : 0); p--) {
                u32 page = adrp_target(tpc(g, p), tw(g, p));
                if (page != NONE && (tw(g, p) & 31) == rn) {
                    u32 v = page + ((s >> 10) & 0xFFF) * 4;
                    if (gv != v)
                        ng++;
                    gv = v;
                    break;
                }
            }
            break;
        }
    }
    if (ng != 1)
        return fail(c, "dvar cg_drawFPS not found; unsupported version");
    int ns = 0;
    for (u32 k = 0; k + 2 < g->n; k++) {
        if (adrp_target(tpc(g, k), tw(g, k)) != (gv & ~0xFFFu) || (tw(g, k) & 31) != 0)
            continue;
        if (tw(g, k + 1) != (0xB9400000 | ((gv & 0xFFF) / 4) << 10))   /* ldr w0, [x0, #lo] */
            continue;
        u32 t = bl_target(tpc(g, k + 2), tw(g, k + 2));
        if (t != NONE) {
            *out = (HookSite){toff(g, k + 2), tpc(g, k + 2), t};
            ns++;
        }
    }
    if (ns != 1)
        return fail(c, "per-frame cg_drawFPS read found %d times; unsupported version", ns);
    return 0;
}

static int perf_detect(Ctx *c, const Guest *g, int *state)
{
    HookSite h;
    TRY(perf_find_hook(c, g, &h));
    *state = h.callee >= code_end(g) ? MOD_ON : MOD_OFF;
    return 0;
}

static int perf_apply(Ctx *c, Guest *g, const Blob *bin)
{
    TRY(watchdog_apply(c, g->nro, g->size));
    HookSite h;
    TRY(perf_find_hook(c, g, &h));
    if (h.callee >= code_end(g))
        return 0;
    u32 refs[4], idx[2], fn[2];
    int nr = string_ref(c, g, "[load] %u ms: zone %s done, %d assets", refs, 4);
    TRY(nr);
    if (nr != 1)
        return fail(c, "port [load] line not found; unsupported version");
    TRY(next_bls(c, g, refs[0], 2, 6, idx, fn));
    if (idx[1] != idx[0] + 1)
        return fail(c, "unexpected log call; unsupported version");
    u32 find;
    TRY(find_dvar_find(c, g, &find));
    if (!bin->data || bin->size < PERF_ENTRY + 4)
        return fail(c, "perf_log.bin missing");
    uint8_t *blob = malloc(bin->size);
    if (!blob)
        return fail(c, "out of memory");
    memcpy(blob, bin->data, bin->size);
    u32 cave = next_code_va(g, 16), state, at;
    if (alloc_bss(c, g, PERF_STATE, &state)) {
        free(blob);
        return -1;
    }
    u32 tbl[8] = {fn[0], fn[1], h.callee, find, state, djb2("r_vsync"), djb2("com_maxfps"), cave};
    for (int i = 0; i < 8; i++)
        wr32(blob + 4 * i, tbl[i]);
    int r = append_code(c, g, blob, bin->size, 16, &at);
    free(blob);
    TRY(r);
    gput(g, h.call_off, enc_bl(h.call_pc, cave + PERF_ENTRY));
    return 0;
}

/* ------------------------------------------------------------------ public */

int mods_detect(const uint8_t *nro, size_t size, int state[MOD_COUNT], char *err, size_t errlen)
{
    Ctx c = {err, errlen};
    Guest g;
    TRY(guest_open(&c, &g, (uint8_t *)nro, size));
    for (int i = 0; i < MOD_COUNT; i++)
        state[i] = MOD_NA;
    if (g.is_mp) {
        TRY(aim_detect(&c, &g, &state[MOD_AIM_ASSIST]));
        TRY(perf_detect(&c, &g, &state[MOD_PERF_LOG]));
    }
    TRY(fps_detect(&c, &g, &state[MOD_FPS_COUNTER]));
    size_t site;
    TRY(nofsync_find(&c, nro, size, &site, &state[MOD_LOG_NOFSYNC]));
    return 0;
}

int mods_apply(uint8_t *nro, size_t size, const int want[MOD_COUNT], const ModBlobs *blobs, char *err, size_t errlen)
{
    Ctx c = {err, errlen};
    Guest g;
    TRY(guest_open(&c, &g, nro, size));
    if ((want[MOD_AIM_ASSIST] || want[MOD_PERF_LOG]) && !g.is_mp)
        return fail(&c, "aim assist and the performance log are multiplayer only");
    /* same order as the scripts: the code cave layout depends on it */
    if (want[MOD_AIM_ASSIST])
        TRY(aim_apply(&c, &g, &blobs->aim_gate));
    if (want[MOD_FPS_COUNTER])
        TRY(fps_apply(&c, &g));
    if (want[MOD_PERF_LOG])
        TRY(perf_apply(&c, &g, &blobs->perf_log));
    if (want[MOD_LOG_NOFSYNC]) {
        size_t site;
        int patched;
        TRY(nofsync_find(&c, nro, size, &site, &patched));
        if (!patched)
            wr32(nro + site, NOP);
    }
    return 0;
}
