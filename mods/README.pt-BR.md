# Mods para o BO2 Requiem NX (Beta 3.2 / 0.3.2)

[English](README.md)

Tudo vai em `/switch/t6game/` no cartão SD. A pasta `sd/` daqui já segue esse layout.

## Aim assist do Zombies no multiplayer

```
python3 patch_mp_aimassist.py /caminho/para/t6mp.nro
```

Grava por cima e deixa `t6mp.nro.bak`. O script procura as instruções por assinatura e recusa versões em que elas não batem. Depois de uma atualização do jogo, rode de novo no `t6mp.nro` novo.

Liga o puxão da mira ao apertar ZL, o lock-on (a mira acompanha o alvo enquanto você mexe o analógico) e um alcance de auto-aim para armas que têm 0. Deixe **AIM ASSIST** ligado em Controles → Gamepad.

O puxão da mira só funciona em partidas contra bots: copie também `sd/switch/t6game/scripts/mp/aim_assist_bots_only.gsc` para `/switch/t6game/scripts/mp/`. O patch só liga o auto-aim quando este console é o servidor e o script diz que todos os outros jogadores são bots (ou jogam no mesmo console, em tela dividida). Se um humano de fora entra, ele desliga em até 1 s. Entrando na partida de outra pessoa ele fica desligado. Sem o script, o auto-aim fica desligado no multiplayer. O modo de sessão não serve para isso: o online do port roda como system link, igual ao Solo e à Private Match. O lock-on e o alcance do auto-aim são à parte: o alcance só é usado pelo auto-aim, e o lock-on não passa pela checagem (não sobra espaço livre no `t6mp.nro` para um segundo gate). Um `t6mp.nro` com o patch antigo (`nop`) é convertido ao rodar o script de novo. A fonte do gate é `aim_gate/aim_gate.c`; `aim_gate/build.sh` recompila o `aim_gate.bin` (precisa do zig).

## Bots nos modos Party

`sd/switch/t6game/scripts/mp/party_bots.gsc` libera bots em Gun Game, One in the Chamber, Sticks & Stones e Sharpshooter. O botão "Setup Bots" continua desativado nesses modos: configure quantidade e dificuldade num modo normal antes de trocar. Se a quantidade estiver em 0, entram 5 bots (`party_bots_default_count()`).

## Launcher novo com configurações e mods (t6game.nro)

```
pip install pillow
launcher/build.sh /caminho/para/t6game.nro.original t6game.nro
```

Substitui o launcher do Requiem por um próprio (libnx, `launcher/source`), com o mesmo visual do fundo original e as opções Multijogador, Zumbis, Configurações, Mods e Atualizações. Os textos seguem o idioma do console: português quando o sistema está em português, inglês nos demais casos. Compila no container `devkitpro/devkita64` (docker). Os assets (fundo, ícone, fontes) são gerados por `launcher/make_assets.py` a partir do NRO original e das fontes DIN Condensed Bold / Avenir Next Condensed do macOS; em outro sistema, use `LAUNCHER_TITLE_FONT`, `LAUNCHER_TEXT_FONT` e os índices das faces.

No SD, renomeie o launcher original para `t6game_orig.nro`: o item **Atualizações** abre ele, que é quem busca e instala versões novas (e pode trocar o `t6game.nro` de volta pelo oficial).

Em **Configurações**:

| Opção | Onde grava |
|---|---|
| Gráfico de desempenho (HUD do DXVK) | `dxvk-sarek.conf` (`dxvk.hud`) |
| Contador de FPS do jogo | `cg_drawFPS` em `players/config_mp.cfg` e `config_zm.cfg` |
| V-Sync | `r_vsync` |
| FPS máximo (30/60) | `com_maxfps` |
| Quadros adiantados (1-3) | `dxvk-sarek.conf` (`dxgi/d3d11.maxFrameLatency`) |
| Campo de visão (65-80) | `cg_fov_default` |
| Bots nos modos Party | `return N;` de `party_bots_default_count()` em `scripts/mp/party_bots.gsc` |

Com o HUD desligado e 1 quadro adiantado, o `dxvk-sarek.conf` é apagado: sem ele o port já força frame latency 1. Com o arquivo presente, o port deixa de forçar, por isso o launcher sempre grava a latência junto.

Em **Mods** dá para ligar e desligar, sem PC, os patches deste README: mira assistida contra bots, contador de FPS (MP e Zumbis), log de desempenho e log sem fsync. A tela lê o `t6mp.nro` e o `t6zm.nro` e mostra o que já está aplicado; ao voltar com B, cada NRO alterado é refeito a partir do original (`t6mp.nro.bak` / `t6zm.nro.bak`, criado na primeira vez), então desligar um mod volta os bytes originais. Depois de uma atualização do jogo, o NRO novo (sem mods) vira o novo `.bak` e basta ligar os mods de novo. Ligar a mira assistida também instala o `scripts/mp/aim_assist_bots_only.gsc`. O código é `launcher/source/nro_patch.c`, que faz os mesmos patches dos scripts Python e gera os mesmos bytes (o `perf_log.bin`, o `aim_gate.bin` e o `.gsc` vão no romfs do launcher). Cada aplicação lê e grava dezenas de MB no SD e leva alguns segundos; o SD precisa de espaço para uma cópia temporária do NRO.

## Contador de FPS com frametime

```
python3 patch_fps_counter.py /caminho/para/t6mp.nro
python3 patch_fps_counter.py /caminho/para/t6zm.nro
```

O contador ligado em Opções → **Mostrar FPS** passa a mostrar `60 fps  16.6 ms  max 33 ms`: FPS, frametime médio e o pior quadro dos últimos 32. Um stutter aparece no `max` por cerca de meio segundo. Pode ser aplicado junto com o patch de aim assist, em qualquer ordem.

## Log de desempenho (multiplayer)

```
python3 patch_perf_log.py /caminho/para/t6mp.nro
```

O `t6mp.log` passa a receber, sem precisar ligar nada no jogo, uma linha `[perf] t=... ms: N frames, avg ... ms, max ... ms, ...` a cada 10 s (quadros, frametime médio e máximo, quantos quadros passaram de 20/34/50/100 ms, V-Sync, Max FPS, custo da escrita no log) e uma linha `[perf] hitch N ms at t=... ms` para cada quadro de 50 ms ou mais (no máximo 4 a cada 10 s). As linhas são em inglês. O `t=` usa o mesmo relógio das linhas `[load]` do port. A fonte é `perf_log/perf_log.c`; `perf_log/build.sh` recompila o `perf_log.bin` (precisa do zig). No `t6zm.nro` não sobra espaço depois do contador de FPS.

## Log sem fsync por linha

```
python3 patch_log_nofsync.py /caminho/para/t6mp.nro
python3 patch_log_nofsync.py /caminho/para/t6zm.nro
```

O port chama fsync depois de cada linha do `t6mp.log`/`t6zm.log`, o que custa uns 17 ms no cartão SD: qualquer linha escrita durante a partida (bots escolhendo classe, o resumo `[perf]`) vira um engasgo. O patch tira esse fsync da função de log do host; as linhas continuam sendo gravadas na hora. O tratador de crash força a gravação por conta própria, então os relatórios `[nx-crash]` continuam completos; só as últimas linhas antes de desligar o console ou tirar o SD podem se perder. Funciona nos dois NROs e junto com os outros patches, em qualquer ordem.

## HUD do DXVK (opcional)

`sd/switch/t6game/dxvk-sarek.conf` liga o HUD do DXVK com `fps,frametimes,gpuload,memory`, para quem não usa o launcher novo (ele grava esse arquivo em **Configurações → Gráfico de desempenho**). Para desligar na mão, apague o arquivo.

## Menus em PT-BR

Use a localização oficial portada por Thermite: <https://github.com/ThermiteK/Call-of-Duty-Black-Ops-2-Port-da-Localizacao-em-Portugues-do-Brasil-Xbox-360-Playstation-3-para-PC/releases>. Do zip, dentro de `CoD_T6mp_T6zm_localizacao_Plutonium/Plutonium/storage/t6/`, copie:

- `raw/localizedstrings/` para `/switch/t6game/raw/localizedstrings/`
- `images/` para `/switch/t6game/images/`

O port lê os `.str` de `raw/localizedstrings` (arquivos `_mp` só no multiplayer, `_zm` só no Zombies).
