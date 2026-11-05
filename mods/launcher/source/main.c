/*
 * Launcher do BO2 Requiem NX com tela de configurações.
 *
 * Desenha num framebuffer 1280x720 (RGBA8888, software) sobre o fundo romfs:/bg.png,
 * com texto via stb_truetype. Escolhe Multijogador/Zumbis (envSetNextLoad do
 * t6mp/t6zm.nro), abre as configurações (settings.c) ou o launcher original
 * (t6game_orig.nro), que é quem busca atualizações.
 */
#include <math.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#include <switch.h>

#define STB_TRUETYPE_IMPLEMENTATION
#include "stb_truetype.h"
#define STB_IMAGE_IMPLEMENTATION
#define STBI_ONLY_PNG
#include "stb_image.h"

#include "settings.h"

#define W 1280
#define H 720
#define X0 110
#define MENU_Y 342      /* 1ª linha do menu principal (o título no fundo fica 208 px acima) */
#define MENU_STEP 44
#define SET_Y 336       /* 1ª linha das configurações */
#define SET_STEP 36
#define VALUE_X 600     /* borda direita dos valores nas configurações */
#define DESC_Y 596
#define HINT_Y 672

typedef struct { u8 r, g, b, a; } Color;
static const Color WHITE = {242, 242, 242, 255}, GRAY = {150, 150, 150, 255}, DIM = {98, 98, 98, 255},
                   ORANGE = {255, 122, 0, 255}, HINT = {190, 190, 190, 255}, BLACK_SHADOW = {0, 0, 0, 150};

static u32 *fbuf;           /* framebuffer atual */
static u32 fstride;         /* em pixels */
static u32 *bg;             /* fundo já convertido */

/* ------------------------------------------------------------------ desenho */

static inline void blend(u32 *p, Color c, int cov)
{
    int a = c.a * cov / 255;
    if (a <= 0)
        return;
    u32 d = *p;
    int dr = d & 0xff, dg = (d >> 8) & 0xff, db = (d >> 16) & 0xff;
    dr += (c.r - dr) * a / 255;
    dg += (c.g - dg) * a / 255;
    db += (c.b - db) * a / 255;
    *p = (u32)dr | (u32)dg << 8 | (u32)db << 16 | 0xff000000u;
}

static void fill_rect(int x, int y, int w, int h, Color c)
{
    for (int yy = y < 0 ? 0 : y; yy < y + h && yy < H; yy++)
        for (int xx = x < 0 ? 0 : x; xx < x + w && xx < W; xx++)
            blend(&fbuf[yy * fstride + xx], c, 255);
}

static void ring(int cx, int cy, float r, float thick, Color c)
{
    for (int y = cy - r - 1; y <= cy + r + 1; y++)
        for (int x = cx - r - 1; x <= cx + r + 1; x++) {
            float d = sqrtf((x - cx) * (x - cx) + (y - cy) * (y - cy));
            float cov = 1.0f - fabsf(d - (r - thick / 2)) / (thick / 2 + 0.5f);
            if (cov > 0 && x >= 0 && y >= 0 && x < W && y < H)
                blend(&fbuf[y * fstride + x], c, (int)(cov * 255));
        }
}

/* triângulo apontando para dir: 0 cima, 1 baixo, 2 esquerda, 3 direita */
static void arrow(int cx, int cy, int s, int dir, Color c)
{
    for (int i = 0; i <= s; i++) {
        int half = i * 7 / 10;
        for (int j = -half; j <= half; j++) {
            int x, y;
            switch (dir) {
            case 0: x = cx + j; y = cy - s / 2 + i; break;
            case 1: x = cx + j; y = cy + s / 2 - i; break;
            case 2: x = cx - s / 2 + i; y = cy + j; break;
            default: x = cx + s / 2 - i; y = cy + j; break;
            }
            if (x >= 0 && y >= 0 && x < W && y < H)
                blend(&fbuf[y * fstride + x], c, 255);
        }
    }
}

/* ------------------------------------------------------------------ texto */

typedef struct {
    stbtt_fontinfo info;
    u8 *data;
} Font;

static Font f_title, f_text, f_bold;

typedef struct {
    const Font *font;
    int px, cp;
    int w, h, xoff, yoff;
    float adv;
    u8 *bmp;
} Glyph;

#define GLYPHS 768
static Glyph glyphs[GLYPHS];
static int nglyphs;

static const Glyph *glyph(const Font *f, int px, int cp)
{
    for (int i = 0; i < nglyphs; i++)
        if (glyphs[i].font == f && glyphs[i].px == px && glyphs[i].cp == cp)
            return &glyphs[i];
    Glyph *g = &glyphs[nglyphs < GLYPHS ? nglyphs++ : GLYPHS - 1];
    if (g->bmp)
        stbtt_FreeBitmap(g->bmp, NULL);
    float s = stbtt_ScaleForPixelHeight(&f->info, px);
    int adv, lsb;
    stbtt_GetCodepointHMetrics(&f->info, cp, &adv, &lsb);
    *g = (Glyph){f, px, cp, 0, 0, 0, 0, adv * s, NULL};
    g->bmp = stbtt_GetCodepointBitmap(&f->info, s, s, cp, &g->w, &g->h, &g->xoff, &g->yoff);
    return g;
}

static int utf8_next(const char **s)
{
    const u8 *p = (const u8 *)*s;
    int cp;
    if (p[0] < 0x80) { cp = p[0]; *s += 1; }
    else if ((p[0] & 0xe0) == 0xc0) { cp = (p[0] & 0x1f) << 6 | (p[1] & 0x3f); *s += 2; }
    else if ((p[0] & 0xf0) == 0xe0) { cp = (p[0] & 0x0f) << 12 | (p[1] & 0x3f) << 6 | (p[2] & 0x3f); *s += 3; }
    else { cp = '?'; *s += 1; }
    return cp;
}

/* altura das maiúsculas, para alinhar textos de fontes diferentes pelo topo */
static int cap_height(const Font *f, int px)
{
    int x0, y0, x1, y1;
    stbtt_GetCodepointBox(&f->info, 'H', &x0, &y0, &x1, &y1);
    return (int)(y1 * stbtt_ScaleForPixelHeight(&f->info, px) + 0.5f);
}

static float text_width(const Font *f, int px, const char *s, float spacing)
{
    float w = 0;
    int first = 1;
    while (*s) {
        int cp = utf8_next(&s);
        w += glyph(f, px, cp)->adv + (first ? 0 : spacing);
        first = 0;
    }
    return w;
}

/* y é o topo das maiúsculas; devolve o x final */
static float draw_text(const Font *f, int px, float x, int y, const char *s, Color c, float spacing)
{
    int base = y + cap_height(f, px);
    while (*s) {
        int cp = utf8_next(&s);
        const Glyph *g = glyph(f, px, cp);
        int gx = (int)(x + 0.5f) + g->xoff, gy = base + g->yoff;
        for (int yy = 0; yy < g->h; yy++) {
            int py = gy + yy;
            if (py < 0 || py >= H)
                continue;
            for (int xx = 0; xx < g->w; xx++) {
                int px_ = gx + xx;
                if (px_ >= 0 && px_ < W && g->bmp[yy * g->w + xx])
                    blend(&fbuf[py * fstride + px_], c, g->bmp[yy * g->w + xx]);
            }
        }
        x += g->adv + spacing;
    }
    return x - spacing;
}

static void draw_shadowed(const Font *f, int px, float x, int y, const char *s, Color c, float spacing)
{
    draw_text(f, px, x + 2, y + 2, s, BLACK_SHADOW, spacing);
    draw_text(f, px, x, y, s, c, spacing);
}

/* texto que quebra linha dentro de max_w */
static void draw_wrapped(const Font *f, int px, int x, int y, int max_w, int line_h, const char *s, Color c)
{
    char line[384] = {0}, word[128];
    while (*s) {
        int n = 0;
        while (*s == ' ')
            s++;
        while (*s && *s != ' ' && n < (int)sizeof word - 1)
            word[n++] = *s++;
        word[n] = 0;
        char tryl[sizeof line + sizeof word + 2];
        snprintf(tryl, sizeof tryl, "%s%s%s", line, line[0] ? " " : "", word);
        if (line[0] && text_width(f, px, tryl, 0) > max_w) {
            draw_text(f, px, x, y, line, c, 0);
            y += line_h;
            snprintf(line, sizeof line, "%s", word);
        } else {
            snprintf(line, sizeof line, "%s", tryl);
        }
    }
    if (line[0])
        draw_text(f, px, x, y, line, c, 0);
}

static int load_font(Font *f, const char *path, int index)
{
    FILE *fp = fopen(path, "rb");
    if (!fp)
        return -1;
    fseek(fp, 0, SEEK_END);
    long n = ftell(fp);
    fseek(fp, 0, SEEK_SET);
    f->data = malloc(n);
    if (!f->data || fread(f->data, 1, n, fp) != (size_t)n) {
        fclose(fp);
        return -1;
    }
    fclose(fp);
    int off = stbtt_GetFontOffsetForIndex(f->data, index);
    return off < 0 || !stbtt_InitFont(&f->info, f->data, off) ? -1 : 0;
}

/* ------------------------------------------------------------------ telas */

enum { SCREEN_MAIN, SCREEN_SETTINGS };
enum { ITEM_MP, ITEM_ZM, ITEM_SETTINGS, ITEM_UPDATES, ITEM_COUNT };

static const char *const ITEM_LABEL[ITEM_COUNT] = {"MULTIJOGADOR", "ZUMBIS", "CONFIGURAÇÕES", "ATUALIZAÇÕES"};
static const char *const ITEM_DESC[ITEM_COUNT] = {
    "Partidas contra bots, system link, tela dividida e servidores online.",
    "Modo Zumbis, com os mapas e mods da pasta do jogo.",
    "Gráfico de desempenho, V-Sync, limite de FPS, campo de visão e bots.",
    "Abre o launcher original do Requiem NX para buscar e instalar atualizações.",
};
static const char *const ITEM_NRO[ITEM_COUNT] = {"t6mp.nro", "t6zm.nro", NULL, "t6game_orig.nro"};

typedef struct {
    int screen;
    int sel, set_sel;
    Option opts[OPT_COUNT];
    int dirty;
    char message[256];      /* aviso no lugar da descrição */
    int app_mode;
    char launch[256];
} State;

static int nro_exists(const char *name)
{
    char p[256];
    snprintf(p, sizeof p, GAME_DIR "/%s", name);
    return access(p, F_OK) == 0;
}

static void hint(float *x, const char *glyph_text, int glyph_kind, const char *label)
{
    int cx = (int)*x + 11, cy = HINT_Y + 11;
    if (glyph_kind == 0) {
        ring(cx, cy, 11, 2, (Color){230, 230, 230, 255});
        float gw = text_width(&f_bold, 17, glyph_text, 0);
        draw_text(&f_bold, 17, cx - gw / 2, cy - cap_height(&f_bold, 17) / 2, glyph_text, (Color){230, 230, 230, 255}, 0);
    } else if (glyph_kind == 1) {
        arrow(cx, cy - 5, 8, 0, (Color){230, 230, 230, 255});
        arrow(cx, cy + 5, 8, 1, (Color){230, 230, 230, 255});
    } else {
        arrow(cx - 5, cy, 8, 2, (Color){230, 230, 230, 255});
        arrow(cx + 5, cy, 8, 3, (Color){230, 230, 230, 255});
    }
    *x = draw_text(&f_bold, 17, *x + 30, HINT_Y + 5, label, HINT, 2) + 34;
}

static void draw_main(const State *s)
{
    draw_text(&f_text, 16, X0, MENU_Y - 30, "SELECIONE O MODO", GRAY, 4);
    fill_rect(X0 - 22, MENU_Y - 4, 4, ITEM_COUNT * MENU_STEP - 8, (Color){255, 122, 0, 70});
    for (int i = 0; i < ITEM_COUNT; i++) {
        int y = MENU_Y + i * MENU_STEP;
        int sel = i == s->sel;
        int missing = ITEM_NRO[i] && !nro_exists(ITEM_NRO[i]);
        Color c = sel ? ORANGE : missing ? DIM : WHITE;
        if (sel)
            fill_rect(X0 - 22, y - 4, 4, 36, ORANGE);
        draw_shadowed(&f_title, 38, X0, y + 3, ITEM_LABEL[i], c, 3);
        fill_rect(X0, y + 39, 440, 1, (Color){255, 255, 255, 22});
    }
    const char *desc = s->message[0] ? s->message : ITEM_DESC[s->sel];
    draw_wrapped(&f_text, 19, X0, DESC_Y, 520, 24, desc, s->message[0] ? ORANGE : GRAY);

    float x = X0 + 40;
    hint(&x, "A", 0, "ABRIR");
    hint(&x, NULL, 1, "NAVEGAR");
    hint(&x, "+", 0, "SAIR");
}

static void draw_settings(const State *s)
{
    draw_text(&f_text, 16, X0, SET_Y - 26, "CONFIGURAÇÕES", GRAY, 4);
    for (int i = 0; i < OPT_COUNT; i++) {
        const Option *o = &s->opts[i];
        int y = SET_Y + i * SET_STEP;
        int sel = i == s->set_sel;
        Color c = !o->available ? DIM : sel ? ORANGE : WHITE;
        if (sel)
            fill_rect(X0 - 22, y - 4, 4, 30, ORANGE);
        draw_text(&f_title, 30, X0, y + 2, o->label, c, 2);
        const char *val = o->available ? o->names[o->value] : "—";
        float vw = text_width(&f_title, 30, val, 2);
        draw_text(&f_title, 30, VALUE_X - vw, y + 2, val, c, 2);
        if (sel && o->available) {
            arrow(VALUE_X - vw - 16, y + 13, 10, 2, ORANGE);
            arrow(VALUE_X + 14, y + 13, 10, 3, ORANGE);
        }
        fill_rect(X0, y + 32, VALUE_X + 24 - X0, 1, (Color){255, 255, 255, 18});
    }
    const Option *o = &s->opts[s->set_sel];
    const char *desc = s->message[0] ? s->message
                     : o->available ? o->desc
                                    : "O arquivo desta opção não existe (scripts/mp/party_bots.gsc).";
    draw_wrapped(&f_text, 19, X0, DESC_Y, 560, 24, desc, s->message[0] ? ORANGE : GRAY);

    float x = X0 + 40;
    hint(&x, NULL, 2, "ALTERAR");
    hint(&x, NULL, 1, "NAVEGAR");
    hint(&x, "B", 0, "SALVAR E VOLTAR");
}

/* ------------------------------------------------------------------ ações */

static void save(State *s)
{
    char err[200];
    if (!s->dirty)
        return;
    if (settings_save(s->opts, err, sizeof err))
        snprintf(s->message, sizeof s->message, "%s", err);
    else
        s->dirty = 0;
}

static int activate(State *s, int item)
{
    s->message[0] = 0;
    if (item == ITEM_SETTINGS) {
        s->screen = SCREEN_SETTINGS;
        return 0;
    }
    const char *name = ITEM_NRO[item];
    if (!nro_exists(name)) {
        snprintf(s->message, sizeof s->message,
                 item == ITEM_UPDATES ? "Falta o launcher original: renomeie o t6game.nro do Requiem para t6game_orig.nro."
                                      : "Falta %s na pasta /switch/t6game.", name);
        return 0;
    }
    if (!s->app_mode && item != ITEM_UPDATES) {
        snprintf(s->message, sizeof s->message,
                 "O jogo precisa do modo aplicativo: abra pelo title takeover (segure R ao abrir um jogo) ou por um forwarder.");
        return 0;
    }
    if (!envHasNextLoad()) {
        snprintf(s->message, sizeof s->message, "Este carregador não permite abrir outro NRO. Abra pelo hbmenu.");
        return 0;
    }
    snprintf(s->launch, sizeof s->launch, GAME_DIR "/%s", name);
    Result rc = envSetNextLoad(s->launch, s->launch);
    if (R_FAILED(rc)) {
        snprintf(s->message, sizeof s->message, "Não deu para abrir %s (0x%08x).", name, rc);
        return 0;
    }
    return 1;
}

static int hit_row(int ty, int first_y, int step, int count)
{
    for (int i = 0; i < count; i++)
        if (ty >= first_y + i * step - 6 && ty < first_y + i * step + step - 6)
            return i;
    return -1;
}

int main(int argc, char **argv)
{
    (void)argc; (void)argv;
    romfsInit();

    int ww, hh, n;
    u8 *img = stbi_load("romfs:/bg.png", &ww, &hh, &n, 4);
    bg = malloc(W * H * 4);
    for (int i = 0; i < W * H; i++)
        bg[i] = img && ww == W && hh == H
              ? img[i * 4] | img[i * 4 + 1] << 8 | img[i * 4 + 2] << 16 | 0xff000000u
              : 0xff0a0807u;
    stbi_image_free(img);

    int idx_text = 5, idx_bold = 0;
    FILE *fi = fopen("romfs:/text.idx", "r");
    if (fi) {
        if (fscanf(fi, "%d %d", &idx_text, &idx_bold) != 2)
            idx_text = 5, idx_bold = 0;
        fclose(fi);
    }
    if (load_font(&f_title, "romfs:/title.ttf", 0) || load_font(&f_text, "romfs:/text.ttf", idx_text) ||
        load_font(&f_bold, "romfs:/text.ttf", idx_bold)) {
        consoleInit(NULL);
        printf("Fontes do launcher ausentes no romfs.\nPressione + para sair.\n");
        PadState pad;
        padConfigureInput(1, HidNpadStyleSet_NpadStandard);
        padInitializeDefault(&pad);
        while (appletMainLoop()) {
            padUpdate(&pad);
            if (padGetButtonsDown(&pad) & HidNpadButton_Plus)
                break;
            consoleUpdate(NULL);
        }
        consoleExit(NULL);
        romfsExit();
        return 0;
    }

    Framebuffer fb;
    framebufferCreate(&fb, nwindowGetDefault(), W, H, PIXEL_FORMAT_RGBA_8888, 2);
    framebufferMakeLinear(&fb);

    padConfigureInput(1, HidNpadStyleSet_NpadStandard);
    PadState pad;
    padInitializeDefault(&pad);
    hidInitializeTouchScreen();

    static State s;
    AppletType at = appletGetAppletType();
    s.app_mode = at == AppletType_Application || at == AppletType_SystemApplication;
    settings_load(s.opts);
    s.sel = nro_exists("t6mp.nro") ? ITEM_MP : ITEM_ZM;

    int prev_touch = 0, quit = 0;
    while (!quit && appletMainLoop()) {
        padUpdate(&pad);
        u64 down = padGetButtonsDown(&pad);

        HidTouchScreenState ts = {0};
        int touch = hidGetTouchScreenStates(&ts, 1) && ts.count > 0;
        int tapped = touch && !prev_touch;
        int tx = touch ? ts.touches[0].x : 0, ty = touch ? ts.touches[0].y : 0;
        prev_touch = touch;

        if (s.screen == SCREEN_MAIN) {
            if (down & HidNpadButton_Plus)
                break;
            if (down & HidNpadButton_AnyUp) { s.sel = (s.sel + ITEM_COUNT - 1) % ITEM_COUNT; s.message[0] = 0; }
            if (down & HidNpadButton_AnyDown) { s.sel = (s.sel + 1) % ITEM_COUNT; s.message[0] = 0; }
            if (down & HidNpadButton_A)
                quit = activate(&s, s.sel);
            if (tapped && tx >= X0 - 30 && tx < X0 + 460) {
                int row = hit_row(ty, MENU_Y, MENU_STEP, ITEM_COUNT);
                if (row >= 0) {
                    s.sel = row;
                    quit = activate(&s, row);
                }
            }
        } else {
            Option *o = &s.opts[s.set_sel];
            int change = 0;
            if (down & (HidNpadButton_B | HidNpadButton_Plus)) {
                s.message[0] = 0;
                save(&s);
                if (!s.message[0])
                    s.screen = SCREEN_MAIN;
            }
            if (down & HidNpadButton_AnyUp) { s.set_sel = (s.set_sel + OPT_COUNT - 1) % OPT_COUNT; s.message[0] = 0; }
            if (down & HidNpadButton_AnyDown) { s.set_sel = (s.set_sel + 1) % OPT_COUNT; s.message[0] = 0; }
            if (down & HidNpadButton_AnyLeft)
                change = -1;
            if (down & (HidNpadButton_AnyRight | HidNpadButton_A))
                change = 1;
            if (tapped && tx >= X0 - 30 && tx < VALUE_X + 40) {
                int row = hit_row(ty, SET_Y, SET_STEP, OPT_COUNT);
                if (row >= 0) {
                    if (row == s.set_sel)
                        change = 1;
                    s.set_sel = row;
                    o = &s.opts[row];
                }
            }
            if (change && o->available) {
                o->value = (o->value + change + o->count) % o->count;
                s.dirty = 1;
                s.message[0] = 0;
            }
        }

        fbuf = framebufferBegin(&fb, &fstride);
        fstride /= 4;
        for (int y = 0; y < H; y++)
            memcpy(&fbuf[y * fstride], &bg[y * W], W * 4);
        if (s.screen == SCREEN_MAIN)
            draw_main(&s);
        else
            draw_settings(&s);
        framebufferEnd(&fb);
    }

    save(&s);
    framebufferClose(&fb);
    romfsExit();
    return 0;
}
