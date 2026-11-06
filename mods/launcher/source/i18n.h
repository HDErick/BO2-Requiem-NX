#pragma once

/* UI strings. English is the default; PT-BR is picked from the console language. */

typedef enum { LANG_EN, LANG_PT_BR, LANG_COUNT } Lang;

typedef enum {
    STR_ITEM_MP,
    STR_ITEM_ZM,
    STR_ITEM_SETTINGS,
    STR_ITEM_UPDATES,
    STR_DESC_MP,
    STR_DESC_ZM,
    STR_DESC_SETTINGS,
    STR_DESC_UPDATES,
    STR_TITLE_MAIN,
    STR_TITLE_SETTINGS,
    STR_HINT_OPEN,
    STR_HINT_NAVIGATE,
    STR_HINT_EXIT,
    STR_HINT_CHANGE,
    STR_HINT_SAVE_BACK,
    STR_OPT_FILE_MISSING,
    STR_ERR_NO_ORIG_LAUNCHER,
    STR_ERR_NRO_MISSING_FMT,
    STR_ERR_NEED_APP_MODE,
    STR_ERR_NO_NEXT_LOAD,
    STR_ERR_LAUNCH_FMT,
    STR_ERR_FONTS_MISSING,
    STR_ERR_WRITE_FMT,
    STR_OFF,
    STR_ON,
    STR_HUD_FPS_FRAMETIME,
    STR_HUD_FULL,
    STR_LATENCY_1,
    STR_OPT_HUD,
    STR_OPT_HUD_DESC,
    STR_OPT_FPS_COUNTER,
    STR_OPT_FPS_COUNTER_DESC,
    STR_OPT_VSYNC,
    STR_OPT_VSYNC_DESC,
    STR_OPT_MAX_FPS,
    STR_OPT_MAX_FPS_DESC,
    STR_OPT_LATENCY,
    STR_OPT_LATENCY_DESC,
    STR_OPT_FOV,
    STR_OPT_FOV_DESC,
    STR_OPT_PARTY_BOTS,
    STR_OPT_PARTY_BOTS_DESC,
    STR_COUNT
} StrId;

/* Picks the language from the system settings; falls back to English. */
void i18n_init(void);

/* Forces a language (host-side tests). */
void i18n_set(Lang l);

const char *tr(StrId id);
