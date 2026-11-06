#include "i18n.h"

#ifdef __SWITCH__
#include <switch.h>
#endif

static const char *const STR_EN[STR_COUNT] = {
    [STR_ITEM_MP] = "MULTIPLAYER",
    [STR_ITEM_ZM] = "ZOMBIES",
    [STR_ITEM_CAMPAIGN] = "CAMPAIGN",
    [STR_DESC_CAMPAIGN] = "The story missions, from bo2-360-nx (the Xbox 360 version, installed in /switch/bo2zm).",
    [STR_ITEM_SETTINGS] = "SETTINGS",
    [STR_ITEM_UPDATES] = "UPDATES",
    [STR_DESC_MP] = "Matches against bots, system link, split screen and online servers.",
    [STR_DESC_ZM] = "Zombies mode, with the maps and mods from the game folder.",
    [STR_DESC_SETTINGS] = "Performance graph, V-Sync, FPS limit, field of view and bots.",
    [STR_DESC_UPDATES] = "Opens the original Requiem NX launcher to check for and install updates.",
    [STR_TITLE_MAIN] = "SELECT A MODE",
    [STR_TITLE_SETTINGS] = "SETTINGS",
    [STR_HINT_OPEN] = "OPEN",
    [STR_HINT_NAVIGATE] = "NAVIGATE",
    [STR_HINT_EXIT] = "EXIT",
    [STR_HINT_CHANGE] = "CHANGE",
    [STR_HINT_SAVE_BACK] = "SAVE AND GO BACK",
    [STR_OPT_FILE_MISSING] = "The file for this option does not exist (scripts/mp/party_bots.gsc).",
    [STR_ERR_NO_ORIG_LAUNCHER] = "Original launcher missing: rename Requiem's t6game.nro to t6game_orig.nro.",
    [STR_ERR_NRO_MISSING_FMT] = "%s is missing from the /switch/t6game folder.",
    [STR_ERR_NEED_APP_MODE] = "The game needs application mode: launch through title takeover (hold R while opening a game) or a forwarder.",
    [STR_ERR_NO_NEXT_LOAD] = "This loader cannot launch another NRO. Open it from hbmenu.",
    [STR_ERR_LAUNCH_FMT] = "Could not open %s (0x%08x).",
    [STR_ERR_FONTS_MISSING] = "Launcher fonts missing from romfs.\nPress + to exit.\n",
    [STR_ERR_WRITE_FMT] = "Could not write %s",
    [STR_OFF] = "Off",
    [STR_ON] = "On",
    [STR_HUD_FPS_FRAMETIME] = "FPS + frametime",
    [STR_HUD_FULL] = "Full",
    [STR_LATENCY_1] = "1 (default)",
    [STR_OPT_HUD] = "Performance graph",
    [STR_OPT_HUD_DESC] = "DXVK HUD in the corner of the screen: FPS, frametime graph, GPU usage and memory.",
    [STR_OPT_FPS_COUNTER] = "In-game FPS counter",
    [STR_OPT_FPS_COUNTER_DESC] = "Same as Options > Show FPS: FPS, average frametime and the worst frame.",
    [STR_OPT_VSYNC] = "V-Sync",
    [STR_OPT_VSYNC_DESC] = "Locks the game to the display refresh (60 Hz). Without it, the 60 FPS cap becomes 62 and the image stutters.",
    [STR_OPT_MAX_FPS] = "Max FPS",
    [STR_OPT_MAX_FPS_DESC] = "Game frame limit (com_maxfps). With V-Sync on, leave it at 60.",
    [STR_OPT_LATENCY] = "Frames queued ahead",
    [STR_OPT_LATENCY_DESC] = "How many frames the CPU may prepare ahead of the GPU. More frames absorb stutters at the cost of slightly more latency.",
    [STR_OPT_FOV] = "Field of view",
    [STR_OPT_FOV_DESC] = "Default FOV for multiplayer and Zombies (cg_fov_default).",
    [STR_OPT_PARTY_BOTS] = "Bots in Party modes",
    [STR_OPT_PARTY_BOTS_DESC] = "How many bots join Gun Game, One in the Chamber, Sticks & Stones and Sharpshooter.",
    [STR_ITEM_MODS] = "MODS",
    [STR_DESC_MODS] = "Turns the t6mp.nro/t6zm.nro patches on and off: aim assist against bots, FPS counter, performance log.",
    [STR_TITLE_MODS] = "MODS",
    [STR_HINT_APPLY_BACK] = "APPLY AND GO BACK",
    [STR_MODS_READING] = "Reading t6mp.nro and t6zm.nro...",
    [STR_MODS_APPLYING] = "Applying the mods. This takes a few seconds...",
    [STR_ERR_READ_FMT] = "Could not read %s",
    [STR_ERR_MODS_UNSUPPORTED_FMT] = "%s: %s",
    [STR_ERR_MODS_NO_BAK_FMT] = "%s has mods but %s.bak (the original) is missing. Put the original NRO back.",
    [STR_ERR_MODS_BAK_MISMATCH_FMT] = "%s does not match %s.bak with its mods (a different version?). Put the original NRO back.",
    [STR_ERR_MODS_OVERLAP_FMT] = "%s has another patch on the same bytes as these mods. Put the original NRO back.",
    [STR_ERR_ROMFS_FMT] = "%s is missing from the launcher.",
    [STR_MOD_AIM_ASSIST] = "Aim assist vs bots",
    [STR_MOD_AIM_ASSIST_DESC] = "Zombies-style aim snap (ZL) and lock-on in multiplayer, only in matches where everyone else is a bot. Also installs scripts/mp/aim_assist_bots_only.gsc.",
    [STR_MOD_FPS_MP] = "FPS counter (MP)",
    [STR_MOD_FPS_ZM] = "FPS counter (Zombies)",
    [STR_MOD_FPS_DESC] = "Options > Show FPS also shows the average frametime and the worst frame.",
    [STR_MOD_PERF_LOG] = "Performance log (MP)",
    [STR_MOD_PERF_LOG_DESC] = "Writes frame time stats to t6mp.log every 10 s and reports freezes from 1 s ([nx-stall]).",
    [STR_MOD_LOG_NOFSYNC] = "Log without fsync",
    [STR_MOD_LOG_NOFSYNC_DESC] = "Stops forcing each t6mp.log/t6zm.log line onto the SD card (about 17 ms each, a visible hitch).",
    [STR_SHORT_AIM_ASSIST] = "aim assist",
    [STR_SHORT_FPS_MP] = "FPS (MP)",
    [STR_SHORT_FPS_ZM] = "FPS (ZM)",
    [STR_SHORT_PERF_LOG] = "perf log",
    [STR_SHORT_LOG_NOFSYNC] = "no fsync",
    [STR_FOOTER_MODS_FMT] = "MODS: %s",
    [STR_FOOTER_NO_MODS] = "NO MODS",
};

static const char *const STR_PT_BR[STR_COUNT] = {
    [STR_ITEM_MP] = "MULTIJOGADOR",
    [STR_ITEM_ZM] = "ZUMBIS",
    [STR_ITEM_CAMPAIGN] = "CAMPANHA",
    [STR_DESC_CAMPAIGN] = "As missões da história, do bo2-360-nx (a versão de Xbox 360, instalada em /switch/bo2zm).",
    [STR_ITEM_SETTINGS] = "CONFIGURAÇÕES",
    [STR_ITEM_UPDATES] = "ATUALIZAÇÕES",
    [STR_DESC_MP] = "Partidas contra bots, system link, tela dividida e servidores online.",
    [STR_DESC_ZM] = "Modo Zumbis, com os mapas e mods da pasta do jogo.",
    [STR_DESC_SETTINGS] = "Gráfico de desempenho, V-Sync, limite de FPS, campo de visão e bots.",
    [STR_DESC_UPDATES] = "Abre o launcher original do Requiem NX para buscar e instalar atualizações.",
    [STR_TITLE_MAIN] = "SELECIONE O MODO",
    [STR_TITLE_SETTINGS] = "CONFIGURAÇÕES",
    [STR_HINT_OPEN] = "ABRIR",
    [STR_HINT_NAVIGATE] = "NAVEGAR",
    [STR_HINT_EXIT] = "SAIR",
    [STR_HINT_CHANGE] = "ALTERAR",
    [STR_HINT_SAVE_BACK] = "SALVAR E VOLTAR",
    [STR_OPT_FILE_MISSING] = "O arquivo desta opção não existe (scripts/mp/party_bots.gsc).",
    [STR_ERR_NO_ORIG_LAUNCHER] = "Falta o launcher original: renomeie o t6game.nro do Requiem para t6game_orig.nro.",
    [STR_ERR_NRO_MISSING_FMT] = "Falta %s na pasta /switch/t6game.",
    [STR_ERR_NEED_APP_MODE] = "O jogo precisa do modo aplicativo: abra pelo title takeover (segure R ao abrir um jogo) ou por um forwarder.",
    [STR_ERR_NO_NEXT_LOAD] = "Este carregador não permite abrir outro NRO. Abra pelo hbmenu.",
    [STR_ERR_LAUNCH_FMT] = "Não deu para abrir %s (0x%08x).",
    [STR_ERR_FONTS_MISSING] = "Fontes do launcher ausentes no romfs.\nPressione + para sair.\n",
    [STR_ERR_WRITE_FMT] = "Não deu para gravar %s",
    [STR_OFF] = "Desligado",
    [STR_ON] = "Ligado",
    [STR_HUD_FPS_FRAMETIME] = "FPS + frametime",
    [STR_HUD_FULL] = "Completo",
    [STR_LATENCY_1] = "1 (padrão)",
    [STR_OPT_HUD] = "Gráfico de desempenho",
    [STR_OPT_HUD_DESC] = "HUD do DXVK no canto da tela: FPS, gráfico de frametime, uso da GPU e memória.",
    [STR_OPT_FPS_COUNTER] = "Contador de FPS do jogo",
    [STR_OPT_FPS_COUNTER_DESC] = "O mesmo de Opções > Mostrar FPS: FPS, frametime médio e o pior quadro.",
    [STR_OPT_VSYNC] = "V-Sync",
    [STR_OPT_VSYNC_DESC] = "Trava o jogo no ritmo da tela (60 Hz). Sem ele, o limite de 60 FPS vira 62 e a imagem engasga.",
    [STR_OPT_MAX_FPS] = "FPS máximo",
    [STR_OPT_MAX_FPS_DESC] = "Limite de quadros do jogo (com_maxfps). Com V-Sync ligado, deixe em 60.",
    [STR_OPT_LATENCY] = "Quadros adiantados",
    [STR_OPT_LATENCY_DESC] = "Quantos quadros a CPU pode preparar antes da GPU. Mais quadros absorvem engasgos, com um pouco mais de atraso.",
    [STR_OPT_FOV] = "Campo de visão",
    [STR_OPT_FOV_DESC] = "FOV padrão do multijogador e do Zumbis (cg_fov_default).",
    [STR_OPT_PARTY_BOTS] = "Bots nos modos Party",
    [STR_OPT_PARTY_BOTS_DESC] = "Quantos bots entram em Gun Game, One in the Chamber, Sticks & Stones e Sharpshooter.",
    [STR_ITEM_MODS] = "MODS",
    [STR_DESC_MODS] = "Liga e desliga os patches do t6mp.nro/t6zm.nro: mira assistida contra bots, contador de FPS, log de desempenho.",
    [STR_TITLE_MODS] = "MODS",
    [STR_HINT_APPLY_BACK] = "APLICAR E VOLTAR",
    [STR_MODS_READING] = "Lendo o t6mp.nro e o t6zm.nro...",
    [STR_MODS_APPLYING] = "Aplicando os mods. Isso leva alguns segundos...",
    [STR_ERR_READ_FMT] = "Não deu para ler %s",
    [STR_ERR_MODS_UNSUPPORTED_FMT] = "%s: %s",
    [STR_ERR_MODS_NO_BAK_FMT] = "O %s tem mods, mas falta o %s.bak (o original). Coloque o NRO original de volta.",
    [STR_ERR_MODS_BAK_MISMATCH_FMT] = "O %s não bate com o %s.bak e seus mods (outra versão?). Coloque o NRO original de volta.",
    [STR_ERR_MODS_OVERLAP_FMT] = "O %s tem outro patch nos mesmos bytes destes mods. Coloque o NRO original de volta.",
    [STR_ERR_ROMFS_FMT] = "Falta %s no launcher.",
    [STR_MOD_AIM_ASSIST] = "Mira assistida (bots)",
    [STR_MOD_AIM_ASSIST_DESC] = "Puxão da mira do Zumbis (ZL) e lock-on no multijogador, só em partidas em que todos os outros são bots. Também instala o scripts/mp/aim_assist_bots_only.gsc.",
    [STR_MOD_FPS_MP] = "Contador de FPS (MP)",
    [STR_MOD_FPS_ZM] = "Contador de FPS (Zumbis)",
    [STR_MOD_FPS_DESC] = "Opções > Mostrar FPS passa a mostrar também o frametime médio e o pior quadro.",
    [STR_MOD_PERF_LOG] = "Log de desempenho (MP)",
    [STR_MOD_PERF_LOG_DESC] = "Grava estatísticas de frametime no t6mp.log a cada 10 s e registra travadas a partir de 1 s ([nx-stall]).",
    [STR_MOD_LOG_NOFSYNC] = "Log sem fsync",
    [STR_MOD_LOG_NOFSYNC_DESC] = "Para de forçar a gravação de cada linha do t6mp.log/t6zm.log no SD (uns 17 ms cada, um engasgo visível).",
    [STR_SHORT_AIM_ASSIST] = "mira assistida",
    [STR_SHORT_FPS_MP] = "FPS (MP)",
    [STR_SHORT_FPS_ZM] = "FPS (ZM)",
    [STR_SHORT_PERF_LOG] = "log de desempenho",
    [STR_SHORT_LOG_NOFSYNC] = "sem fsync",
    [STR_FOOTER_MODS_FMT] = "MODS: %s",
    [STR_FOOTER_NO_MODS] = "SEM MODS",
};

static const char *const *const TABLES[LANG_COUNT] = {[LANG_EN] = STR_EN, [LANG_PT_BR] = STR_PT_BR};

static Lang cur = LANG_EN;

void i18n_set(Lang l) { cur = l >= 0 && l < LANG_COUNT ? l : LANG_EN; }

void i18n_init(void)
{
    cur = LANG_EN;
#ifdef __SWITCH__
    if (R_FAILED(setInitialize()))
        return;
    u64 code = 0;
    SetLanguage lang;
    if (R_SUCCEEDED(setGetSystemLanguage(&code)) && R_SUCCEEDED(setMakeLanguage(code, &lang)) &&
        (lang == SetLanguage_PTBR || lang == SetLanguage_PT))
        cur = LANG_PT_BR;
    setExit();
#endif
}

const char *tr(StrId id)
{
    if (id < 0 || id >= STR_COUNT)
        return "";
    const char *s = TABLES[cur][id];
    return s ? s : STR_EN[id] ? STR_EN[id] : "";
}
