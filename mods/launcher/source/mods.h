#pragma once
/*
 * Mods screen: turns the binary patches (nro_patch.c) on and off in t6mp.nro / t6zm.nro
 * on the SD card. The original of each NRO is kept as <name>.nro.bak (like the Python
 * scripts do); every change rebuilds the NRO from it, so turning a mod off restores the
 * original bytes. After a game update the new, unpatched NRO becomes the new .bak.
 */
#include <stddef.h>

#include "nro_patch.h"
#include "settings.h"

enum { GAME_MP, GAME_ZM, GAME_COUNT };

typedef struct {
    int present;            /* the NRO exists */
    int supported;          /* mods_detect() accepted it */
    int state[MOD_COUNT];   /* applied now (MOD_ON / MOD_OFF / MOD_NA) */
    int want[MOD_COUNT];    /* chosen on the screen */
    char err[160];          /* why it is not supported */
} ModGame;

enum { MROW_AIM_ASSIST, MROW_FPS_MP, MROW_FPS_ZM, MROW_PERF_LOG, MROW_LOG_NOFSYNC, MROW_CFG_BUFFER, MROW_COUNT };

/* Reads both NROs (tens of MB each: a few seconds) and detects the applied mods.
 * Safe to run on a background thread; setting mods_cancel makes it stop early (the
 * results are then incomplete). */
void mods_load(ModGame games[GAME_COUNT]);
extern volatile int mods_cancel;

/* Display version from the NACP of t6mp.nro (or t6zm.nro), e.g. "0.3.2". */
int mods_game_version(char *buf, size_t len);

/* Comma-separated short names of the applied mods ("" if none). */
const char *mods_summary(const ModGame games[GAME_COUNT], char *buf, size_t len);

/* Rows for the screen: value 1 = on. Call after i18n_init. */
void mods_rows(const ModGame games[GAME_COUNT], Option rows[MROW_COUNT]);

/* Applies a row change to the wanted state. */
void mods_set(ModGame games[GAME_COUNT], int row, int on);

/* Nonzero if some wanted state differs from the applied one. */
int mods_dirty(const ModGame games[GAME_COUNT]);

/* Rewrites the NROs whose wanted state changed. Returns 0, or -1 with the reason in err. */
int mods_save(ModGame games[GAME_COUNT], char *err, size_t errlen);
