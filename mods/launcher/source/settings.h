#pragma once
#include <stddef.h>

#ifndef GAME_DIR
#define GAME_DIR "sdmc:/switch/t6game"
#endif

enum {
    OPT_HUD,
    OPT_FPS_COUNTER,
    OPT_VSYNC,
    OPT_MAX_FPS,
    OPT_LATENCY,
    OPT_FOV,
    OPT_PARTY_BOTS,
    OPT_COUNT
};

typedef struct {
    const char *label;
    const char *desc;
    const char *const *names;
    int count;
    int value;       /* index into names */
    int available;   /* 0: the option cannot be changed (see missing) */
    const char *missing; /* shown instead of desc when not available */
} Option;

/* Reads current values from players/config_*.cfg, dxvk-sarek.conf and scripts/mp/party_bots.gsc.
 * Call after i18n_init: labels and value names are resolved here. */
void settings_load(Option *opts);

/* Writes the changes. Returns 0 on success; otherwise writes the reason into err. */
int settings_save(const Option *opts, char *err, size_t errlen);
