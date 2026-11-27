#include "settings.h"
#include "i18n.h"

#include <ctype.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#define CFG_MP     GAME_DIR "/players/config_mp.cfg"
#define CFG_ZM     GAME_DIR "/players/config_zm.cfg"
#define DXVK_CONF  GAME_DIR "/dxvk-sarek.conf"
#define PARTY_GSC  GAME_DIR "/scripts/mp/party_bots.gsc"

/* Translated names are filled in settings_load, after i18n_init. */
static const char *HUD_NAMES[4];
static const char *const HUD_VALUES[] = {"", "fps", "fps,frametimes", "fps,frametimes,gpuload,memory"};
static const char *ONOFF[2];
static const char *const MAX_FPS_NAMES[] = {"30", "60"};
static const int MAX_FPS_VALUES[] = {30, 60};
static const char *LATENCY_NAMES[] = {NULL, "2", "3"};
static const char *const FOV_NAMES[] = {"65", "70", "75", "80"};
static const int FOV_VALUES[] = {65, 70, 75, 80};
static const char *const BOTS_NAMES[] = {"3", "5", "7", "9"};
static const int BOTS_VALUES[] = {3, 5, 7, 9};

#define N(a) ((int)(sizeof(a) / sizeof((a)[0])))

/* ------------------------------------------------------------------ files */

static char *read_file(const char *path, size_t *len)
{
    FILE *f = fopen(path, "rb");
    if (!f)
        return NULL;
    fseek(f, 0, SEEK_END);
    long n = ftell(f);
    fseek(f, 0, SEEK_SET);
    char *buf = malloc(n + 1);
    if (!buf || fread(buf, 1, n, f) != (size_t)n) {
        free(buf);
        fclose(f);
        return NULL;
    }
    fclose(f);
    buf[n] = 0;
    if (len)
        *len = n;
    return buf;
}

/* write to .tmp and swap, so a power loss never leaves a half-written file */
static int write_file(const char *path, const char *data, size_t len)
{
    char tmp[256];
    snprintf(tmp, sizeof tmp, "%s.tmp", path);
    FILE *f = fopen(tmp, "wb");
    if (!f)
        return -1;
    int ok = fwrite(data, 1, len, f) == len;
    ok &= fclose(f) == 0;
    if (!ok) {
        remove(tmp);
        return -1;
    }
    remove(path);
    return rename(tmp, path);
}

static int exists(const char *path) { return access(path, F_OK) == 0; }

/* ------------------------------------------------------------------ config_*.cfg */

/* value of `seta name "value"`; returns 0 if not found */
static int cfg_get(const char *cfg, const char *name, char *out, size_t outlen)
{
    size_t nl = strlen(name);
    for (const char *p = cfg; p && *p; p = strchr(p, '\n') ? strchr(p, '\n') + 1 : NULL) {
        if (strncmp(p, "seta ", 5) || strncmp(p + 5, name, nl) || p[5 + nl] != ' ' || p[6 + nl] != '"')
            continue;
        const char *v = p + 7 + nl, *e = strchr(v, '"');
        if (!e)
            return 0;
        size_t n = (size_t)(e - v) < outlen - 1 ? (size_t)(e - v) : outlen - 1;
        memcpy(out, v, n);
        out[n] = 0;
        return 1;
    }
    return 0;
}

/* new copy of cfg with `seta name "value"` replaced (or appended at the end) */
static char *cfg_set(const char *cfg, const char *name, const char *value)
{
    size_t nl = strlen(name), cl = strlen(cfg);
    char line[160];
    int ll = snprintf(line, sizeof line, "seta %s \"%s\"", name, value);
    char *out = malloc(cl + ll + 4);
    if (!out)
        return NULL;
    for (const char *p = cfg; *p;) {
        const char *eol = strchr(p, '\n');
        const char *end = eol ? eol : p + strlen(p);
        if (!strncmp(p, "seta ", 5) && !strncmp(p + 5, name, nl) && p[5 + nl] == ' ') {
            const char *cr = (end > p && end[-1] == '\r') ? "\r" : "";
            size_t pre = p - cfg;
            memcpy(out, cfg, pre);
            int n = sprintf(out + pre, "%s%s", line, cr);
            strcpy(out + pre + n, end);
            return out;
        }
        p = eol ? eol + 1 : end;
    }
    /* not found: append at the end */
    strcpy(out, cfg);
    if (cl && out[cl - 1] != '\n')
        strcat(out, "\n");
    strcat(out, line);
    strcat(out, "\n");
    return out;
}

/* ------------------------------------------------------------------ load */

static int index_of_int(const int *values, int count, int v, int fallback)
{
    for (int i = 0; i < count; i++)
        if (values[i] == v)
            return i;
    return fallback;
}

void settings_load(Option *o)
{
    HUD_NAMES[0] = tr(STR_OFF);
    HUD_NAMES[1] = "FPS";
    HUD_NAMES[2] = tr(STR_HUD_FPS_FRAMETIME);
    HUD_NAMES[3] = tr(STR_HUD_FULL);
    ONOFF[0] = tr(STR_OFF);
    ONOFF[1] = tr(STR_ON);
    LATENCY_NAMES[0] = tr(STR_LATENCY_1);

    o[OPT_HUD] = (Option){tr(STR_OPT_HUD), tr(STR_OPT_HUD_DESC), HUD_NAMES, N(HUD_NAMES), 0, 1, NULL};
    o[OPT_FPS_COUNTER] = (Option){tr(STR_OPT_FPS_COUNTER), tr(STR_OPT_FPS_COUNTER_DESC), ONOFF, 2, 1, 1, NULL};
    o[OPT_VSYNC] = (Option){tr(STR_OPT_VSYNC), tr(STR_OPT_VSYNC_DESC), ONOFF, 2, 1, 1, NULL};
    o[OPT_MAX_FPS] = (Option){tr(STR_OPT_MAX_FPS), tr(STR_OPT_MAX_FPS_DESC), MAX_FPS_NAMES, N(MAX_FPS_NAMES), 1, 1, NULL};
    o[OPT_LATENCY] = (Option){tr(STR_OPT_LATENCY), tr(STR_OPT_LATENCY_DESC), LATENCY_NAMES, N(LATENCY_NAMES), 0, 1, NULL};
    o[OPT_FOV] = (Option){tr(STR_OPT_FOV), tr(STR_OPT_FOV_DESC), FOV_NAMES, N(FOV_NAMES), 0, 1, NULL};
    o[OPT_PARTY_BOTS] = (Option){tr(STR_OPT_PARTY_BOTS), tr(STR_OPT_PARTY_BOTS_DESC), BOTS_NAMES, N(BOTS_NAMES), 1, 1,
                                 tr(STR_OPT_FILE_MISSING)};

    char v[64];
    char *cfg = read_file(CFG_MP, NULL);
    if (!cfg)
        cfg = read_file(CFG_ZM, NULL);
    if (cfg) {
        if (cfg_get(cfg, "cg_drawFPS", v, sizeof v))
            o[OPT_FPS_COUNTER].value = strcmp(v, "Off") != 0;
        if (cfg_get(cfg, "r_vsync", v, sizeof v))
            o[OPT_VSYNC].value = atoi(v) != 0;
        if (cfg_get(cfg, "com_maxfps", v, sizeof v))
            o[OPT_MAX_FPS].value = index_of_int(MAX_FPS_VALUES, N(MAX_FPS_VALUES), atoi(v), 1);
        if (cfg_get(cfg, "cg_fov_default", v, sizeof v))
            o[OPT_FOV].value = index_of_int(FOV_VALUES, N(FOV_VALUES), atoi(v), 0);
        free(cfg);
    }

    /* without the file the port forces frame latency 1 and leaves the HUD off */
    char *conf = read_file(DXVK_CONF, NULL);
    if (conf) {
        for (char *p = conf; p && *p; p = strchr(p, '\n') ? strchr(p, '\n') + 1 : NULL) {
            while (*p == ' ' || *p == '\t')
                p++;
            char *eq = strchr(p, '='), *eol = strchr(p, '\n');
            if (!eq || (eol && eq > eol))
                continue;
            char *val = eq + 1;
            while (*val == ' ')
                val++;
            size_t vl = eol ? (size_t)(eol - val) : strlen(val);
            while (vl && isspace((unsigned char)val[vl - 1]))
                vl--;
            if (!strncmp(p, "dxvk.hud", 8)) {
                char hud[96] = {0};
                memcpy(hud, val, vl < sizeof hud - 1 ? vl : sizeof hud - 1);
                o[OPT_HUD].value = strstr(hud, "gpuload") ? 3 : strstr(hud, "frametimes") ? 2 : strstr(hud, "fps") ? 1 : 0;
            } else if (!strncmp(p, "dxgi.maxFrameLatency", 20)) {
                int n = atoi(val);
                o[OPT_LATENCY].value = n >= 1 && n <= 3 ? n - 1 : 0;
            }
        }
        free(conf);
    }

    char *gsc = read_file(PARTY_GSC, NULL);
    if (gsc) {
        char *f = strstr(gsc, "party_bots_default_count()");
        char *r = f ? strstr(f, "return ") : NULL;
        o[OPT_PARTY_BOTS].value = r ? index_of_int(BOTS_VALUES, N(BOTS_VALUES), atoi(r + 7), 1) : 1;
        o[OPT_PARTY_BOTS].available = r != NULL;
        free(gsc);
    } else {
        o[OPT_PARTY_BOTS].available = 0;
    }
}

/* ------------------------------------------------------------------ save */

static int save_cfg(const char *path, const Option *o)
{
    size_t len;
    char *cfg = read_file(path, &len);
    if (!cfg) {
        cfg = strdup("");
        if (!cfg)
            return -1;
    }
    char fps[16], fov[16];
    snprintf(fps, sizeof fps, "%d", MAX_FPS_VALUES[o[OPT_MAX_FPS].value]);
    snprintf(fov, sizeof fov, "%d", FOV_VALUES[o[OPT_FOV].value]);
    const char *names[] = {"cg_drawFPS", "r_vsync", "com_maxfps", "cg_fov_default"};
    const char *values[] = {o[OPT_FPS_COUNTER].value ? "Simple" : "Off", o[OPT_VSYNC].value ? "1" : "0", fps, fov};
    for (int i = 0; i < 4; i++) {
        char *next = cfg_set(cfg, names[i], values[i]);
        free(cfg);
        if (!next)
            return -1;
        cfg = next;
    }
    int r = write_file(path, cfg, strlen(cfg));
    free(cfg);
    return r;
}

static int save_dxvk(const Option *o)
{
    int hud = o[OPT_HUD].value, lat = o[OPT_LATENCY].value + 1;
    if (hud == 0 && lat == 1) {
        remove(DXVK_CONF);  /* port default: no file */
        return 0;
    }
    char buf[512];
    int n = snprintf(buf, sizeof buf,
                     "# Generated by the launcher (Settings). Delete it to go back to the port's default.\n"
                     "dxgi.maxFrameLatency = %d\n"
                     "d3d11.maxFrameLatency = %d\n",
                     lat, lat);
    if (hud)
        n += snprintf(buf + n, sizeof buf - n, "dxvk.hud = %s\n", HUD_VALUES[hud]);
    return write_file(DXVK_CONF, buf, n);
}

static int save_party_bots(const Option *o)
{
    size_t len;
    char *gsc = read_file(PARTY_GSC, &len);
    if (!gsc)
        return -1;
    char *f = strstr(gsc, "party_bots_default_count()");
    char *r = f ? strstr(f, "return ") : NULL;
    if (!r) {
        free(gsc);
        return -1;
    }
    char *num = r + 7, *end = num;
    while (isdigit((unsigned char)*end))
        end++;
    char *out = malloc(len + 16);
    if (!out) {
        free(gsc);
        return -1;
    }
    size_t pre = num - gsc;
    memcpy(out, gsc, pre);
    int n = sprintf(out + pre, "%d", BOTS_VALUES[o[OPT_PARTY_BOTS].value]);
    strcpy(out + pre + n, end);
    int res = write_file(PARTY_GSC, out, strlen(out));
    free(out);
    free(gsc);
    return res;
}

int settings_save(const Option *o, char *err, size_t errlen)
{
    if (save_cfg(CFG_MP, o)) {
        snprintf(err, errlen, tr(STR_ERR_WRITE_FMT), CFG_MP);
        return -1;
    }
    if (exists(CFG_ZM) && save_cfg(CFG_ZM, o)) {
        snprintf(err, errlen, tr(STR_ERR_WRITE_FMT), CFG_ZM);
        return -1;
    }
    if (save_dxvk(o)) {
        snprintf(err, errlen, tr(STR_ERR_WRITE_FMT), DXVK_CONF);
        return -1;
    }
    if (o[OPT_PARTY_BOTS].available && save_party_bots(o)) {
        snprintf(err, errlen, tr(STR_ERR_WRITE_FMT), PARTY_GSC);
        return -1;
    }
    return 0;
}
