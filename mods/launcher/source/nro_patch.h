#pragma once
/*
 * The mods/patch_*.py binary patches, in C, for the launcher's Mods screen.
 *
 * Same signatures, same order and the same bytes as the Python scripts: applying a set
 * of mods to an original NRO here gives the same file as running the scripts on it in
 * the order patch_mp_aimassist, patch_fps_counter, patch_perf_log, patch_log_nofsync.
 * No libnx: also builds on the host for tests.
 */
#include <stddef.h>
#include <stdint.h>

typedef enum {
    MOD_AIM_ASSIST,     /* patch_mp_aimassist.py (t6mp only; needs aim_gate.bin) */
    MOD_FPS_COUNTER,    /* patch_fps_counter.py (t6mp and t6zm) */
    MOD_PERF_LOG,       /* patch_perf_log.py (t6mp only; needs perf_log.bin) */
    MOD_LOG_NOFSYNC,    /* patch_log_nofsync.py (t6mp and t6zm) */
    MOD_COUNT
} ModId;

enum { MOD_NA = -1, MOD_OFF = 0, MOD_ON = 1 };

typedef struct {
    const uint8_t *data;
    size_t size;
} Blob;

typedef struct {
    Blob perf_log;      /* perf_log/perf_log.bin */
    Blob aim_gate;      /* aim_gate/aim_gate.bin */
} ModBlobs;

/* State of each mod in this NRO: MOD_ON, MOD_OFF, or MOD_NA when it does not apply to
 * this game (e.g. aim assist in t6zm). Returns 0, or -1 with the reason in err when the
 * NRO is not a supported version. */
int mods_detect(const uint8_t *nro, size_t size, int state[MOD_COUNT], char *err, size_t errlen);

/* Applies the mods with want[i] != 0 to an NRO without any of them, in place (the size
 * does not change). Returns 0, or -1 with the reason in err (nro may be half patched). */
int mods_apply(uint8_t *nro, size_t size, const int want[MOD_COUNT], const ModBlobs *blobs, char *err,
               size_t errlen);
