# Mods para o BO2 Requiem NX (Beta 3.2 / 0.3.2)

Tudo vai em `/switch/t6game/` no cartão SD. A pasta `sd/` daqui já segue esse layout.

## Aim assist do Zombies no multiplayer

```
python3 patch_mp_aimassist.py /caminho/para/t6mp.nro
```

Grava por cima e deixa `t6mp.nro.bak`. O script procura as instruções por assinatura e recusa versões em que elas não batem. Depois de uma atualização do jogo, rode de novo no `t6mp.nro` novo.

Liga o puxão da mira ao apertar ZL, o lock-on (a mira acompanha o alvo enquanto você mexe o analógico) e um alcance de auto-aim para armas que têm 0. Deixe **AIM ASSIST** ligado em Controles → Gamepad.

## Bots nos modos Party

`sd/switch/t6game/scripts/mp/party_bots.gsc` libera bots em Gun Game, One in the Chamber, Sticks & Stones e Sharpshooter. O botão "Setup Bots" continua desativado nesses modos: configure quantidade e dificuldade num modo normal antes de trocar. Se a quantidade estiver em 0, entram 5 bots (`party_bots_default_count()`).

## Contador de FPS com frametime

```
python3 patch_fps_counter.py /caminho/para/t6mp.nro
python3 patch_fps_counter.py /caminho/para/t6zm.nro
```

O contador ligado em Opções → **Mostrar FPS** passa a mostrar `60 fps  16.6 ms  max 33 ms`: FPS, frametime médio e o pior quadro dos últimos 32. Um stutter aparece no `max` por cerca de meio segundo. Pode ser aplicado junto com o patch de aim assist, em qualquer ordem.

## HUD do DXVK (opcional)

`sd/switch/t6game/dxvk-sarek.conf` liga o HUD do DXVK com `fps,frametimes,gpuload,memory`. Ele não tem opção no menu: para desligar, apague o arquivo.

## Menus em PT-BR

Use a localização oficial portada por Thermite: <https://github.com/ThermiteK/Call-of-Duty-Black-Ops-2-Port-da-Localizacao-em-Portugues-do-Brasil-Xbox-360-Playstation-3-para-PC/releases>. Do zip, dentro de `CoD_T6mp_T6zm_localizacao_Plutonium/Plutonium/storage/t6/`, copie:

- `raw/localizedstrings/` para `/switch/t6game/raw/localizedstrings/`
- `images/` para `/switch/t6game/images/`

O port lê os `.str` de `raw/localizedstrings` (arquivos `_mp` só no multiplayer, `_zm` só no Zombies).
