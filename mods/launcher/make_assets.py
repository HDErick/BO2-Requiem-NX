#!/usr/bin/env python3
"""Gera o romfs do launcher a partir do t6game.nro original.

  romfs/bg.png       fundo 1280x720: textura e logo R do launcherBG.png original,
                     lado esquerdo escurecido, brilho no logo, título e faixa de rodapé
  romfs/title.ttf    fonte dos títulos e itens (DIN Condensed Bold no macOS)
  romfs/text.ttf     fonte dos textos menores (Avenir Next Condensed no macOS; .ttc serve)
  romfs/text.idx     índices das faces normal e negrito dentro de text.ttf
  icon.jpg           ícone do NRO original

Nada disso vai para o repositório: o fundo e o ícone são do port, e as fontes são do
sistema. Outras fontes: LAUNCHER_TITLE_FONT / LAUNCHER_TEXT_FONT (.ttf ou .ttc),
LAUNCHER_TEXT_FONT_INDEX e LAUNCHER_TEXT_FONT_BOLD_INDEX.

Uso: python3 make_assets.py caminho/para/t6game.nro pasta_de_saida
"""
import io
import os
import struct
import sys

from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 1280, 720
X0, HEADER_Y = 110, 134          # precisa bater com o layout de source/main.c
ORANGE = (255, 122, 0)
TITLE_FONT = os.environ.get("LAUNCHER_TITLE_FONT", "/System/Library/Fonts/Supplemental/DIN Condensed Bold.ttf")
TEXT_FONT = os.environ.get("LAUNCHER_TEXT_FONT", "/System/Library/Fonts/Avenir Next Condensed.ttc")
TEXT_FONT_INDEX = int(os.environ.get("LAUNCHER_TEXT_FONT_INDEX", "5"))       # Medium no .ttc do macOS
TEXT_FONT_BOLD_INDEX = int(os.environ.get("LAUNCHER_TEXT_FONT_BOLD_INDEX", "0"))  # Bold


def nro_assets(path):
    """(ícone JPEG, launcherBG.png) do NRO original."""
    nro = open(path, "rb").read()
    if nro[0x10:0x14] != b"NRO0":
        raise SystemExit("não é um NRO")
    aset = struct.unpack_from("<I", nro, 0x18)[0]
    if nro[aset:aset + 4] != b"ASET":
        raise SystemExit("NRO sem ASET")
    icon_off, icon_size, _, _, rom_off, _ = struct.unpack_from("<6Q", nro, aset + 8)
    rom = nro[aset + rom_off:]
    hdr = struct.unpack_from("<10Q", rom, 0)
    fm_off, fm_size, data_off = hdr[7], hdr[8], hdr[9]
    files, pos = {}, 0
    while pos < fm_size:
        _, _, foff, fsize, _, nlen = struct.unpack_from("<IIQQII", rom, fm_off + pos)
        name = rom[fm_off + pos + 32:fm_off + pos + 32 + nlen].decode()
        files[name] = rom[data_off + foff:data_off + foff + fsize]
        pos += 32 + ((nlen + 3) & ~3)
    if "launcherBG.png" not in files:
        raise SystemExit("launcherBG.png não está no romfs; não parece o t6game.nro original")
    return nro[aset + icon_off:aset + icon_off + icon_size], files["launcherBG.png"]


def spaced(draw, xy, text, fnt, fill, spacing):
    x, y = xy
    for ch in text:
        draw.text((x, y), ch, font=fnt, fill=fill)
        x += draw.textlength(ch, font=fnt) + spacing
    return x


def make_background(orig):
    img = orig.convert("RGB").resize((W, H)).convert("RGBA")

    # lado esquerdo escurecido para o texto; o logo da direita continua visível
    shade = Image.new("L", (W, H))
    shade.putdata([int(235 * (max(0.0, 1.0 - x / 820.0) ** 1.4)) for _ in range(H) for x in range(W)])
    img = Image.composite(Image.new("RGBA", (W, H), (6, 7, 9, 255)), img, shade)

    # brilho laranja atrás do logo
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse((800, 120, 1180, 580), fill=ORANGE + (70,))
    img = Image.alpha_composite(img, glow.filter(ImageFilter.GaussianBlur(90)))

    # vinheta em cima e faixa escura embaixo
    over = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    od = ImageDraw.Draw(over)
    for y in range(110):
        od.line((0, y, W, y), fill=(0, 0, 0, int(120 * (1 - y / 110))))
    for y in range(632, H):
        od.line((0, y, W, y), fill=(0, 0, 0, int(200 * min(1, (y - 632) / 40))))
    od.line((0, 648, W, 648), fill=(255, 255, 255, 28))
    img = Image.alpha_composite(img, over)

    d = ImageDraw.Draw(img)
    title = ImageFont.truetype(TITLE_FONT, 104)
    d.text((X0 + 4, HEADER_Y + 4), "BLACK OPS II", font=title, fill=(0, 0, 0, 160))
    d.text((X0, HEADER_Y), "BLACK OPS II", font=title, fill=(245, 245, 245, 255))
    sub = ImageFont.truetype(TEXT_FONT, 26, index=TEXT_FONT_BOLD_INDEX)
    x = spaced(d, (X0 + 2, HEADER_Y + 106), "REQUIEM", sub, ORANGE + (255,), 7)
    spaced(d, (x + 14, HEADER_Y + 106), "NX", sub, (235, 235, 235, 255), 7)
    d.line((X0, HEADER_Y + 154, X0 + 440, HEADER_Y + 154), fill=(255, 255, 255, 40), width=1)
    d.line((X0, HEADER_Y + 154, X0 + 64, HEADER_Y + 154), fill=ORANGE + (255,), width=3)
    return img.convert("RGB")


def main():
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    icon, bg = nro_assets(sys.argv[1])
    out = sys.argv[2]
    os.makedirs(os.path.join(out, "romfs"), exist_ok=True)
    make_background(Image.open(io.BytesIO(bg))).save(os.path.join(out, "romfs", "bg.png"), optimize=True)
    open(os.path.join(out, "icon.jpg"), "wb").write(icon)
    open(os.path.join(out, "romfs", "title.ttf"), "wb").write(open(TITLE_FONT, "rb").read())
    open(os.path.join(out, "romfs", "text.ttf"), "wb").write(open(TEXT_FONT, "rb").read())
    open(os.path.join(out, "romfs", "text.idx"), "w").write(f"{TEXT_FONT_INDEX} {TEXT_FONT_BOLD_INDEX}\n")
    print(f"assets em {out}")


if __name__ == "__main__":
    main()
