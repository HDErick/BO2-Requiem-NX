#include "mods.h"
#include "i18n.h"

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

#ifndef ROMFS
#define ROMFS "romfs:/"
#endif

static const char *const NRO_NAME[GAME_COUNT] = {"t6mp.nro", "t6zm.nro"};
#define GATE_GSC "aim_assist_bots_only.gsc"
#define CHUNK (1 << 20)

volatile int mods_cancel;

/* ------------------------------------------------------------------ files */

static uint8_t *load(const char *path, size_t *len)
{
    FILE *f = fopen(path, "rb");
    if (!f)
        return NULL;
    fseek(f, 0, SEEK_END);
    long n = ftell(f);
    fseek(f, 0, SEEK_SET);
    uint8_t *buf = n > 0 ? malloc(n) : NULL;
    size_t got = 0;
    while (buf && got < (size_t)n && !mods_cancel) {
        size_t r = fread(buf + got, 1, (size_t)n - got < CHUNK ? (size_t)n - got : CHUNK, f);
        if (!r)
            break;
        got += r;
    }
    fclose(f);
    if (!buf || got != (size_t)n) {
        free(buf);
        return NULL;
    }
    *len = n;
    return buf;
}

/* compares the file with buf without loading it whole */
static int same_file(const char *path, const uint8_t *buf, size_t len)
{
    FILE *f = fopen(path, "rb");
    if (!f)
        return 0;
    uint8_t *chunk = malloc(CHUNK);
    size_t pos = 0;
    int same = chunk != NULL;
    while (same && pos < len) {
        size_t want = len - pos < CHUNK ? len - pos : CHUNK;
        same = fread(chunk, 1, want, f) == want && !memcmp(chunk, buf + pos, want);
        pos += want;
    }
    same = same && fgetc(f) == EOF;
    free(chunk);
    fclose(f);
    return same;
}

/* write to .tmp and swap, so a power loss never leaves a half-written NRO */
static int save_file(const char *path, const uint8_t *data, size_t len)
{
    char tmp[300];
    snprintf(tmp, sizeof tmp, "%s.tmp", path);
    FILE *f = fopen(tmp, "wb");
    if (!f)
        return -1;
    size_t done = 0;
    while (done < len) {
        size_t w = fwrite(data + done, 1, len - done < CHUNK ? len - done : CHUNK, f);
        if (!w)
            break;
        done += w;
    }
    int ok = done == len;
    ok &= fclose(f) == 0;
    if (!ok) {
        remove(tmp);
        return -1;
    }
    remove(path);
    return rename(tmp, path);
}

static void nro_path(char *out, size_t len, int game, const char *suffix)
{
    snprintf(out, len, GAME_DIR "/%s%s", NRO_NAME[game], suffix);
}

int mods_game_version(char *out, size_t len)
{
    /* display version of the NACP in the NRO's ASET section */
    for (int g = 0; g < GAME_COUNT; g++) {
        char path[300];
        nro_path(path, sizeof path, g, "");
        FILE *f = fopen(path, "rb");
        if (!f)
            continue;
        uint8_t hdr[0x20], aset[0x38], ver[0x10];
        int ok = fread(hdr, 1, sizeof hdr, f) == sizeof hdr && !memcmp(hdr + 0x10, "NRO0", 4);
        uint32_t asoff = ok ? (uint32_t)(hdr[0x18] | hdr[0x19] << 8 | hdr[0x1A] << 16 | (uint32_t)hdr[0x1B] << 24) : 0;
        ok = ok && !fseek(f, asoff, SEEK_SET) && fread(aset, 1, sizeof aset, f) == sizeof aset && !memcmp(aset, "ASET", 4);
        uint64_t nacp = 0;
        for (int i = 7; ok && i >= 0; i--)
            nacp = nacp << 8 | aset[0x18 + i];
        ok = ok && !fseek(f, (long)(asoff + nacp + 0x3060), SEEK_SET) && fread(ver, 1, sizeof ver, f) == sizeof ver;
        fclose(f);
        if (ok && ver[0]) {
            snprintf(out, len, "%.*s", (int)sizeof ver, (const char *)ver);
            return 0;
        }
    }
    return -1;
}

/* ------------------------------------------------------------------ load */

void mods_load(ModGame games[GAME_COUNT])
{
    for (int g = 0; g < GAME_COUNT; g++) {
        ModGame *m = &games[g];
        memset(m, 0, sizeof *m);
        for (int i = 0; i < MOD_COUNT; i++)
            m->state[i] = m->want[i] = MOD_NA;
        char path[300];
        nro_path(path, sizeof path, g, "");
        size_t len;
        uint8_t *nro = load(path, &len);
        m->present = nro != NULL || access(path, F_OK) == 0;
        if (!nro) {
            if (m->present)
                snprintf(m->err, sizeof m->err, tr(STR_ERR_READ_FMT), NRO_NAME[g]);
            continue;
        }
        m->supported = mods_detect(nro, len, m->state, m->err, sizeof m->err) == 0;
        free(nro);
        memcpy(m->want, m->state, sizeof m->want);
    }
}

/* ------------------------------------------------------------------ rows */

static const char *ONOFF[2];

static int usable(const ModGame *m, int mod) { return m->present && m->supported && m->state[mod] != MOD_NA; }

static const char *why_not(const ModGame games[GAME_COUNT], int game, char *buf, size_t len)
{
    const ModGame *m = &games[game];
    if (!m->present)
        snprintf(buf, len, tr(STR_ERR_NRO_MISSING_FMT), NRO_NAME[game]);
    else
        snprintf(buf, len, tr(STR_ERR_MODS_UNSUPPORTED_FMT), NRO_NAME[game], m->err);
    return buf;
}

void mods_rows(const ModGame games[GAME_COUNT], Option rows[MROW_COUNT])
{
    static char why[MROW_COUNT][224];
    static const struct { int game, mod; StrId label, desc; } ROWS[MROW_COUNT] = {
        [MROW_AIM_ASSIST] = {GAME_MP, MOD_AIM_ASSIST, STR_MOD_AIM_ASSIST, STR_MOD_AIM_ASSIST_DESC},
        [MROW_FPS_MP] = {GAME_MP, MOD_FPS_COUNTER, STR_MOD_FPS_MP, STR_MOD_FPS_DESC},
        [MROW_FPS_ZM] = {GAME_ZM, MOD_FPS_COUNTER, STR_MOD_FPS_ZM, STR_MOD_FPS_DESC},
        [MROW_PERF_LOG] = {GAME_MP, MOD_PERF_LOG, STR_MOD_PERF_LOG, STR_MOD_PERF_LOG_DESC},
        [MROW_LOG_NOFSYNC] = {GAME_MP, MOD_LOG_NOFSYNC, STR_MOD_LOG_NOFSYNC, STR_MOD_LOG_NOFSYNC_DESC},
    };
    ONOFF[0] = tr(STR_OFF);
    ONOFF[1] = tr(STR_ON);
    for (int r = 0; r < MROW_COUNT; r++) {
        int game = ROWS[r].game, mod = ROWS[r].mod;
        /* the log row covers both games: shown from Zombies when multiplayer is not usable */
        if (r == MROW_LOG_NOFSYNC && !usable(&games[GAME_MP], mod) && usable(&games[GAME_ZM], mod))
            game = GAME_ZM;
        const ModGame *m = &games[game];
        int ok = usable(m, mod);
        rows[r] = (Option){tr(ROWS[r].label), tr(ROWS[r].desc), ONOFF, 2, ok && m->want[mod] == MOD_ON, ok,
                           ok ? NULL : why_not(games, game, why[r], sizeof why[r])};
    }
}

void mods_set(ModGame games[GAME_COUNT], int row, int on)
{
    int v = on ? MOD_ON : MOD_OFF;
    switch (row) {
    case MROW_AIM_ASSIST: games[GAME_MP].want[MOD_AIM_ASSIST] = v; break;
    case MROW_FPS_MP: games[GAME_MP].want[MOD_FPS_COUNTER] = v; break;
    case MROW_FPS_ZM: games[GAME_ZM].want[MOD_FPS_COUNTER] = v; break;
    case MROW_PERF_LOG: games[GAME_MP].want[MOD_PERF_LOG] = v; break;
    case MROW_LOG_NOFSYNC:
        for (int g = 0; g < GAME_COUNT; g++)
            if (usable(&games[g], MOD_LOG_NOFSYNC))
                games[g].want[MOD_LOG_NOFSYNC] = v;
        break;
    }
}

static int game_dirty(const ModGame *m)
{
    return m->present && m->supported && memcmp(m->want, m->state, sizeof m->want) != 0;
}

int mods_dirty(const ModGame games[GAME_COUNT])
{
    for (int g = 0; g < GAME_COUNT; g++)
        if (game_dirty(&games[g]))
            return 1;
    return 0;
}

const char *mods_summary(const ModGame games[GAME_COUNT], char *buf, size_t len)
{
    static const struct { int game, mod; StrId name; } APPLIED[] = {
        {GAME_MP, MOD_AIM_ASSIST, STR_SHORT_AIM_ASSIST}, {GAME_MP, MOD_FPS_COUNTER, STR_SHORT_FPS_MP},
        {GAME_ZM, MOD_FPS_COUNTER, STR_SHORT_FPS_ZM},    {GAME_MP, MOD_PERF_LOG, STR_SHORT_PERF_LOG},
    };
    size_t n = 0;
    buf[0] = 0;
    for (size_t i = 0; i < sizeof APPLIED / sizeof APPLIED[0]; i++)
        if (games[APPLIED[i].game].state[APPLIED[i].mod] == MOD_ON)
            n += snprintf(buf + n, n < len ? len - n : 0, "%s%s", n ? ", " : "", tr(APPLIED[i].name));
    if (games[GAME_MP].state[MOD_LOG_NOFSYNC] == MOD_ON || games[GAME_ZM].state[MOD_LOG_NOFSYNC] == MOD_ON)
        n += snprintf(buf + n, n < len ? len - n : 0, "%s%s", n ? ", " : "", tr(STR_SHORT_LOG_NOFSYNC));
    return buf;
}

/* ------------------------------------------------------------------ save */

static int any_on(const int state[MOD_COUNT])
{
    for (int i = 0; i < MOD_COUNT; i++)
        if (state[i] == MOD_ON)
            return 1;
    return 0;
}

/* Rebuilds one NRO from its original with the wanted mods. */
static int rebuild(int game, ModGame *m, const ModBlobs *blobs, char *err, size_t errlen)
{
    char path[300], bak[300], why[160];
    nro_path(path, sizeof path, game, "");
    nro_path(bak, sizeof bak, game, ".bak");
    const char *name = NRO_NAME[game];

    size_t len;
    uint8_t *nro = load(path, &len);
    int st[MOD_COUNT];
    if (!nro) {
        snprintf(err, errlen, tr(STR_ERR_READ_FMT), name);
        return -1;
    }
    if (mods_detect(nro, len, st, why, sizeof why)) {
        free(nro);
        snprintf(err, errlen, tr(STR_ERR_MODS_UNSUPPORTED_FMT), name, why);
        return -1;
    }
    if (!any_on(st)) {
        /* unpatched (first time, or a game update): this is the original */
        if (!same_file(bak, nro, len) && save_file(bak, nro, len)) {
            free(nro);
            snprintf(err, errlen, tr(STR_ERR_WRITE_FMT), bak);
            return -1;
        }
    } else {
        free(nro);
        nro = load(bak, &len);
        if (!nro) {
            snprintf(err, errlen, tr(STR_ERR_MODS_NO_BAK_FMT), name, name);
            return -1;
        }
        if (mods_detect(nro, len, st, why, sizeof why) || any_on(st)) {
            free(nro);
            snprintf(err, errlen, tr(STR_ERR_MODS_BAK_PATCHED_FMT), name);
            return -1;
        }
    }

    int want[MOD_COUNT];
    for (int i = 0; i < MOD_COUNT; i++)
        want[i] = m->want[i] == MOD_ON;
    if (mods_apply(nro, len, want, blobs, why, sizeof why)) {
        free(nro);
        snprintf(err, errlen, tr(STR_ERR_MODS_UNSUPPORTED_FMT), name, why);
        return -1;
    }
    int r = save_file(path, nro, len);
    free(nro);
    if (r) {
        snprintf(err, errlen, tr(STR_ERR_WRITE_FMT), path);
        return -1;
    }
    memcpy(m->state, m->want, sizeof m->state);
    return 0;
}

/* the aim assist gate reads a dvar that this script keeps on the host */
static int install_gate_script(char *err, size_t errlen)
{
    const char *dst = GAME_DIR "/scripts/mp/" GATE_GSC;
    if (access(dst, F_OK) == 0)
        return 0;
    size_t len;
    uint8_t *gsc = load(ROMFS GATE_GSC, &len);
    if (!gsc) {
        snprintf(err, errlen, tr(STR_ERR_ROMFS_FMT), GATE_GSC);
        return -1;
    }
    mkdir(GAME_DIR "/scripts", 0777);
    mkdir(GAME_DIR "/scripts/mp", 0777);
    int r = save_file(dst, gsc, len);
    free(gsc);
    if (r)
        snprintf(err, errlen, tr(STR_ERR_WRITE_FMT), dst);
    return r;
}

int mods_save(ModGame games[GAME_COUNT], char *err, size_t errlen)
{
    size_t plen = 0, glen = 0;
    uint8_t *perf = load(ROMFS "perf_log.bin", &plen), *gate = load(ROMFS "aim_gate.bin", &glen);
    ModBlobs blobs = {{perf, plen}, {gate, glen}};
    int r = 0;
    for (int g = 0; g < GAME_COUNT && !r; g++)
        if (game_dirty(&games[g]))
            r = rebuild(g, &games[g], &blobs, err, errlen);
    if (!r && games[GAME_MP].state[MOD_AIM_ASSIST] == MOD_ON)
        r = install_gate_script(err, errlen);
    free(perf);
    free(gate);
    return r;
}
