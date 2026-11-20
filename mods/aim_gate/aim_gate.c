/*
 * Bot-match gate for the multiplayer aim assist of the BO2 Requiem NX t6mp_guest.elf.
 *
 * AimAssist_IsAutoAimActive() only goes on with the SESSIONMODE_ZOMBIES bit set. The
 * patcher replaces that `tbz w3, #4, <exit>` with a `b aa_entry`: Zombies keeps the stock
 * path, and in multiplayer auto-aim is only allowed while
 *   - this console runs the server (sv_running), and
 *   - the dvar nx_aimassist_allowed is nonzero. scripts/mp/aim_assist_bots_only.gsc sets it
 *     on the host: 1 while every other player is a bot or local to the host, 0 otherwise.
 * When joining someone else's match sv_running is 0, so a stale value of the script dvar
 * never enables it. The port's online play runs as SESSIONMODE_SYSTEMLINK (like Solo and
 * Private Match), so the session mode alone cannot tell a bot match from an online one.
 *
 * The patched function is a leaf: it keeps w0, w1, x2, x4 and w5 live across this point
 * and the callers may rely on other registers too, so the entry saves every caller-saved
 * register (x0-x17, q0-q7, q16-q31) around the call into C.
 *
 * Layout (the patcher depends on it): table at 0x00, `b <allow>` at 0x18, `b <deny>` at
 * 0x1c (filled in by the patcher), entry at 0x20. Same position-independent build and
 * load-offset fixup as perf_log.c.
 */
#include <stdint.h>

typedef uint32_t u32;

struct gate_tbl {
    u32 dvar_find;   /* dvar_t *Dvar_FindVarByHash(u32) */
    u32 dvar_int;    /* int Dvar_GetInt(dvar_t *): bool, int and string ("1") dvars */
    u32 state;       /* 8 bytes of .bss: cached dvar pointers */
    u32 h_running;   /* hash of sv_running */
    u32 h_allowed;   /* hash of nx_aimassist_allowed */
    u32 self;        /* VA of this table in the ELF */
};

__attribute__((section(".text.tbl"), used)) volatile struct gate_tbl gate_tbl;

#define T ((const volatile struct gate_tbl *)&gate_tbl)
#define BASE ((u32)((uintptr_t)&gate_tbl - T->self))
#define S ((volatile u32 *)(uintptr_t)(u32)(T->state + BASE))
#define FN(type, field) ((type)(uintptr_t)(u32)(T->field + BASE))

typedef u32 (*find_fn)(u32);
typedef int (*int_fn)(u32);

/* Dvars are never freed: once found, the pointer is kept. */
static u32 dvar(volatile u32 *slot, u32 hash)
{
    u32 dv = *slot;
    if (!dv) {
        dv = FN(find_fn, dvar_find)(hash);
        *slot = dv;
    }
    return dv;
}

__attribute__((used)) int aa_allowed(void)
{
    volatile u32 *s = S;
    u32 running = dvar(&s[0], T->h_running);
    if (!running || !FN(int_fn, dvar_int)(running))
        return 0;
    u32 allowed = dvar(&s[1], T->h_allowed);
    return allowed && FN(int_fn, dvar_int)(allowed);
}

__asm__(
    ".section .text.slots,\"ax\"\n"
    "gate_allow: b gate_allow\n"          /* -> stock code after the session check */
    "gate_deny:  b gate_deny\n"           /* -> the stock `ret` (auto-aim off) */
    ".section .text.entry,\"ax\"\n"
    ".global aa_entry\n"
    "aa_entry:\n"
    "    tbnz w3, #4, gate_allow\n"       /* Zombies: unchanged */
    "    sub sp, sp, #0x220\n"
    "    stp x29, x30, [sp, #0x00]\n"
    "    mov x29, sp\n"
    "    stp x0, x1, [sp, #0x10]\n"
    "    stp x2, x3, [sp, #0x20]\n"
    "    stp x4, x5, [sp, #0x30]\n"
    "    stp x6, x7, [sp, #0x40]\n"
    "    stp x8, x9, [sp, #0x50]\n"
    "    stp x10, x11, [sp, #0x60]\n"
    "    stp x12, x13, [sp, #0x70]\n"
    "    stp x14, x15, [sp, #0x80]\n"
    "    stp x16, x17, [sp, #0x90]\n"
    "    stp q0, q1, [sp, #0xa0]\n"
    "    stp q2, q3, [sp, #0xc0]\n"
    "    stp q4, q5, [sp, #0xe0]\n"
    "    stp q6, q7, [sp, #0x100]\n"
    "    stp q16, q17, [sp, #0x120]\n"
    "    stp q18, q19, [sp, #0x140]\n"
    "    stp q20, q21, [sp, #0x160]\n"
    "    stp q22, q23, [sp, #0x180]\n"
    "    stp q24, q25, [sp, #0x1a0]\n"
    "    stp q26, q27, [sp, #0x1c0]\n"
    "    stp q28, q29, [sp, #0x1e0]\n"
    "    stp q30, q31, [sp, #0x200]\n"
    "    bl aa_allowed\n"
    "    str x0, [sp, #0x28]\n"           /* the result comes back in x3 */
    "    ldp q30, q31, [sp, #0x200]\n"
    "    ldp q28, q29, [sp, #0x1e0]\n"
    "    ldp q26, q27, [sp, #0x1c0]\n"
    "    ldp q24, q25, [sp, #0x1a0]\n"
    "    ldp q22, q23, [sp, #0x180]\n"
    "    ldp q20, q21, [sp, #0x160]\n"
    "    ldp q18, q19, [sp, #0x140]\n"
    "    ldp q16, q17, [sp, #0x120]\n"
    "    ldp q6, q7, [sp, #0x100]\n"
    "    ldp q4, q5, [sp, #0xe0]\n"
    "    ldp q2, q3, [sp, #0xc0]\n"
    "    ldp q0, q1, [sp, #0xa0]\n"
    "    ldp x16, x17, [sp, #0x90]\n"
    "    ldp x14, x15, [sp, #0x80]\n"
    "    ldp x12, x13, [sp, #0x70]\n"
    "    ldp x10, x11, [sp, #0x60]\n"
    "    ldp x8, x9, [sp, #0x50]\n"
    "    ldp x6, x7, [sp, #0x40]\n"
    "    ldp x4, x5, [sp, #0x30]\n"
    "    ldp x2, x3, [sp, #0x20]\n"
    "    ldp x0, x1, [sp, #0x10]\n"
    "    ldp x29, x30, [sp, #0x00]\n"
    "    add sp, sp, #0x220\n"
    "    cbz w3, gate_deny\n"
    "    b gate_allow\n");
