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
    int value;       /* índice em names */
    int available;   /* 0: o arquivo que guarda a opção não existe */
} Option;

/* Lê os valores atuais de players/config_*.cfg, dxvk-sarek.conf e scripts/mp/party_bots.gsc. */
void settings_load(Option *opts);

/* Grava o que mudou. Devolve 0 em sucesso; senão escreve o motivo em err. */
int settings_save(const Option *opts, char *err, size_t errlen);
