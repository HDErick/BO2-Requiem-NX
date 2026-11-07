/*
 * Buffered config writes for the BO2 Requiem NX t6mp/t6zm_guest.elf.
 *
 * Com_WriteConfigToFile() writes players/config_mp.cfg (config_zm.cfg) one FS_Printf()
 * per line (one `seta` per dvar, then the key bindings). The port's fwrite goes straight to
 * a write() on the SD card, ~10-13 ms each, so the ~250 lines freeze the game for ~3 s
 * every time an archived dvar changes (lobby, Setup Bots, after a map loads, on quit).
 *
 * The patcher redirects three spots in Com_WriteConfigToFile / FS_Printf here:
 *   cfg_begin  replaces `mov w20, w0` after the file is opened: remembers the handle
 *   cfg_write  replaces FS_Printf's `bl FS_Write`: lines for that handle are gathered in a
 *              buffer at the end of .bss and written in blocks; anything else goes on to
 *              FS_Write unchanged
 *   cfg_end    replaces the tail call to FS_FCloseFile: writes what is left, then closes
 * The file content is the same, written in a handful of FS_Write calls instead of hundreds.
 *
 * Layout (the patcher depends on it): table at 0x00, `b cfg_begin` at 0x10,
 * `b cfg_write` at 0x14, `b cfg_end` at 0x18. Same position-independent build and
 * load-offset fixup as perf_log.c. The code cave after the code segment is nearly full in
 * t6mp (and t6zm), so the patcher puts this blob over the last bytes of .eh_frame: the
 * guest has no unwinder and nothing in it or in the host reads that section.
 */
#include <stdint.h>

typedef uint32_t u32;

#define CAP 0x400   /* must match CFG_STATE in the patchers (header 12 bytes + CAP) */

struct cfg_tbl {
    u32 fs_write;   /* int FS_Write(const void *buf, int len, int h) */
    u32 fs_close;   /* void FS_FCloseFile(int h) */
    u32 state;      /* struct cfg_state in .bss */
    u32 self;       /* VA of this table in the ELF */
};

struct cfg_state {
    u32 on;         /* a config file is being written */
    u32 h;          /* its handle */
    u32 n;          /* bytes in buf */
    unsigned char buf[CAP];
};

__attribute__((section(".text.tbl"), used)) volatile struct cfg_tbl cfg_tbl;

#define T ((const volatile struct cfg_tbl *)&cfg_tbl)
#define BASE ((u32)((uintptr_t)&cfg_tbl - T->self))
#define S ((volatile struct cfg_state *)(uintptr_t)(u32)(T->state + BASE))
#define FN(type, field) ((type)(uintptr_t)(u32)(T->field + BASE))

typedef int (*write_fn)(u32, int, u32);
typedef void (*close_fn)(u32);

static void flush(volatile struct cfg_state *s)
{
    if (s->n)
        FN(write_fn, fs_write)((u32)(uintptr_t)s->buf, (int)s->n, s->h);
    s->n = 0;
}

__attribute__((used)) int cfg_write(u32 buf, int len, u32 h)
{
    volatile struct cfg_state *s = S;
    if (!s->on || s->h != h || len <= 0)
        return FN(write_fn, fs_write)(buf, len, h);
    if (s->n + (u32)len > CAP) {
        flush(s);
        if ((u32)len > CAP)
            return FN(write_fn, fs_write)(buf, len, h);
    }
    const unsigned char *src = (const unsigned char *)(uintptr_t)buf;
    for (int i = 0; i < len; i++)
        s->buf[s->n + i] = src[i];
    s->n += len;
    return len;
}

__attribute__((used)) void cfg_end(u32 h)
{
    volatile struct cfg_state *s = S;
    if (s->on && s->h == h)
        flush(s);
    s->on = 0;
    FN(close_fn, fs_close)(h);
}

__asm__(
    ".section .text.slots,\"ax\"\n"
    ".global cfg_slots\n"
    "cfg_slots:\n"
    "    b cfg_begin\n"
    "    b cfg_write\n"
    "    b cfg_end\n"
    ".text\n"
    /* in place of `mov w20, w0`: keeps x0 and x1 (FS_Printf's arguments come next) */
    "cfg_begin:\n"
    "    mov w20, w0\n"
    "    adr x16, cfg_tbl\n"
    "    ldr w17, [x16, #12]\n"
    "    sub w17, w16, w17\n"
    "    ldr w16, [x16, #8]\n"
    "    add w16, w16, w17\n"
    "    str w0, [x16, #4]\n"
    "    str wzr, [x16, #8]\n"
    "    mov w17, #1\n"
    "    str w17, [x16]\n"
    "    ret\n");
