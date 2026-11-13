/*
 * Per-frame performance log for the BO2 Requiem NX t6mp_guest.elf.
 *
 * Replaces the Dvar_GetInt(cg_drawFPS) call that the port's SCR makes once per
 * frame: it measures the frame interval with cntpct_el0 and returns the dvar's
 * original value. Every 10 s it writes a summary line to t6mp.log; frames of 50 ms
 * or more also get a line of their own (at most 4 per window).
 *
 * The code is position-independent (-mcmodel=tiny): the patcher copies the blob to
 * any address and fills the `perf_tbl` table with this build's VAs. The host loads
 * the guest (PIE) at an offset, so the table VAs are fixed up at run time by the
 * difference between the table's real address and `self`.
 * Guest pointers are 32-bit but the code is LP64: addresses below 4 GB work the
 * same in x registers.
 */
#include <stdint.h>

typedef uint32_t u32;
typedef uint64_t u64;

struct perf_tbl {
    u32 va;          /* char *va(const char *fmt, ...) */
    u32 nx_log;      /* void nx_log(const char *line): one line in t6mp.log */
    u32 dvar_get;    /* int Dvar_GetInt(dvar_t *): the original call */
    u32 dvar_find;   /* dvar_t *Dvar_FindVarByHash(u32) */
    u32 state;       /* 64 free bytes of .bss */
    u32 h_vsync;     /* hash of r_vsync */
    u32 h_maxfps;    /* hash of com_maxfps */
    u32 self;        /* VA of this table in the ELF */
};

struct perf_state {
    u64 last;        /* cntpct of the previous frame */
    u64 win_start;
    u64 sum_us;
    u32 max_us;
    u32 frames;
    u32 c20, c34, c50, c100;
    u32 logged;      /* hitch lines in this window */
    u32 log_us;      /* worst cost of one log write in the previous window */
    u32 inited;
};

__attribute__((section(".text.tbl"), used)) volatile struct perf_tbl perf_tbl;

#define T ((const volatile struct perf_tbl *)&perf_tbl)
/* guest load offset: real table address minus the VA written by the patcher */
#define BASE ((u32)((uintptr_t)&perf_tbl - T->self))
#define S ((volatile struct perf_state *)(uintptr_t)(u32)(T->state + BASE))
#define FN(type, field) ((type)(uintptr_t)(u32)(T->field + BASE))

typedef char *(*va_fn)(const char *, ...);
typedef void (*log_fn)(const char *);
typedef int (*get_fn)(u32);
typedef u32 (*find_fn)(u32);

static inline u64 ticks(void)
{
    u64 t;
    __asm__ volatile("isb; mrs %0, cntpct_el0" : "=r"(t));
    return t;
}

/* 19.2 MHz: us = ticks * 5 / 96; ms from the same clock as the "[load] %u ms" lines */
static inline u32 to_us(u64 t) { return (u32)(t * 5 / 96); }
static inline u32 to_ms(u64 t) { return (u32)(t / 19200); }

static int dvar_int(u32 hash)
{
    u32 dv = FN(find_fn, dvar_find)(hash);
    return dv ? *(volatile int *)(uintptr_t)(dv + 0x18) : -1;
}

static void log_line(const char *line)
{
    u64 a = ticks();
    FN(log_fn, nx_log)(line);
    u32 cost = to_us(ticks() - a);
    if (cost > S->log_us)
        S->log_us = cost;
}

__attribute__((section(".text.entry"))) int perf_frame(u32 dvar)
{
    volatile struct perf_state *s = S;
    u64 now = ticks();

    if (!s->inited) {
        s->inited = 1;
        s->last = now;
        s->win_start = now;
        return FN(get_fn, dvar_get)(dvar);
    }

    u32 dt = to_us(now - s->last);
    s->frames++;
    s->sum_us += dt;
    if (dt > s->max_us)
        s->max_us = dt;
    if (dt >= 20000) s->c20++;
    if (dt >= 34000) s->c34++;
    if (dt >= 50000) s->c50++;
    if (dt >= 100000) s->c100++;

    int wrote = 0;
    if (dt >= 50000 && s->logged < 4) {
        s->logged++;
        log_line(FN(va_fn, va)("[perf] hitch %u ms at t=%u ms", dt / 1000, to_ms(now)));
        wrote = 1;
    }

    if (now - s->win_start >= 10ull * 19200000ull) {
        u32 n = s->frames;
        u32 avg = (u32)(s->sum_us / n);
        u32 prev_log = s->log_us;
        s->log_us = 0;
        log_line(FN(va_fn, va)(
            "[perf] t=%u ms: %u frames, avg %u.%02u ms, max %u.%u ms, >=20ms %u, >=34ms %u, "
            ">=50ms %u, >=100ms %u, vsync %d, maxfps %d, log %u us",
            to_ms(now), n, avg / 1000, (avg % 1000) / 10, s->max_us / 1000, (s->max_us % 1000) / 100,
            s->c20, s->c34, s->c50, s->c100, dvar_int(T->h_vsync), dvar_int(T->h_maxfps), prev_log));
        s->win_start = now;
        s->sum_us = 0;
        s->max_us = 0;
        s->frames = 0;
        s->c20 = s->c34 = s->c50 = s->c100 = 0;
        s->logged = 0;
        wrote = 1;
    }

    /* time spent writing the log does not count toward the next frame */
    s->last = wrote ? ticks() : now;
    return FN(get_fn, dvar_get)(dvar);
}
