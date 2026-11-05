#!/usr/bin/env python3
"""Tela inicial nova para o t6game.nro (o launcher que escolhe Multijogador/Zumbis).

O launcher desenha, num framebuffer 1280x720:
  - romfs:/launcherBG.png de fundo;
  - startSP/MP/ZM.png em x=110, y=286/330/374, no tamanho do próprio PNG (o toque usa
    o mesmo tamanho). O item selecionado é recolorido pela luminância para laranja,
    por isso os textos são claros;
  - "CHECK FOR UPDATES" centralizado em y=348 e a versão em (24, 684), com a fonte dele.

O script gera fundo e itens a partir do launcherBG.png original (reaproveita a textura e
o logo R), reconstrói o romfs com os PNGs novos e muda o botão de atualização para o
canto inferior direito, com o texto "VERIFICAR UPDATES" (mesmo tamanho da string).

Precisa do Pillow (pip install pillow) e das fontes DIN Condensed Bold e Avenir Next
Condensed do macOS; outras fontes podem ser passadas por LAUNCHER_TITLE_FONT e
LAUNCHER_TEXT_FONT.

Uso: python3 patch_launcher.py caminho/para/t6game.nro [saida.nro]
"""
import io
import os
import struct
import sys

from PIL import Image, ImageDraw, ImageFilter, ImageFont
from PIL.PngImagePlugin import PngInfo

from nro_guest import write_nro

W, H = 1280, 720
ITEM_X, ITEM_STEP = 110, 44
ITEM_Y_OLD, ITEM_Y = 286, 342  # o launcher desenha o 1º item em y=286; o patch desce o menu
ORANGE = (255, 122, 0)
UPDATE_CX, UPDATE_Y, UPDATE_H = 1110, 668, 22
OLD_UPDATE_TEXT, NEW_UPDATE_TEXT = b"CHECK FOR UPDATES\0", b"VERIFICAR UPDATES\0"
MARKER = "requiem-nx-mods launcher"

TITLE_FONT = os.environ.get("LAUNCHER_TITLE_FONT", "/System/Library/Fonts/Supplemental/DIN Condensed Bold.ttf")
TEXT_FONT = os.environ.get("LAUNCHER_TEXT_FONT", "/System/Library/Fonts/Avenir Next Condensed.ttc")


def font(path, size, index=0):
    return ImageFont.truetype(path, size, index=index)


def text_font(size, bold=True):
    # Avenir Next Condensed.ttc: 0 = Bold, 2 = Demi Bold, 5 = Medium
    return font(TEXT_FONT, size, 0 if bold else 5)


def spaced(draw, xy, text, fnt, fill, spacing):
    x, y = xy
    for ch in text:
        draw.text((x, y), ch, font=fnt, fill=fill)
        x += draw.textlength(ch, font=fnt) + spacing
    return x


def spaced_width(draw, text, fnt, spacing):
    return sum(draw.textlength(ch, font=fnt) for ch in text) + spacing * (len(text) - 1)


def make_background(orig):
    base = orig.convert("RGB").resize((W, H))
    img = base.convert("RGBA")

    # lado esquerdo escurecido para o texto; o logo da direita continua visível
    shade = Image.new("L", (W, H))
    sp = shade.load()
    for x in range(W):
        a = max(0.0, 1.0 - x / 820.0)
        v = int(235 * (a ** 1.4))
        for y in range(H):
            sp[x, y] = v
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

    # título (posições relativas à primeira linha do menu)
    top = ITEM_Y - 208
    title = font(TITLE_FONT, 104)
    d.text((ITEM_X + 4, top + 4), "BLACK OPS II", font=title, fill=(0, 0, 0, 160))
    d.text((ITEM_X, top), "BLACK OPS II", font=title, fill=(245, 245, 245, 255))
    sub = text_font(26)
    x = spaced(d, (ITEM_X + 2, top + 106), "REQUIEM", sub, ORANGE + (255,), 7)
    spaced(d, (x + 14, top + 106), "NX", sub, (235, 235, 235, 255), 7)
    d.line((ITEM_X, top + 154, ITEM_X + 440, top + 154), fill=(255, 255, 255, 40), width=1)
    d.line((ITEM_X, top + 154, ITEM_X + 64, top + 154), fill=ORANGE + (255,), width=3)

    # menu
    spaced(d, (ITEM_X, top + 172), "SELECIONE O MODO", text_font(16, bold=False), (150, 150, 150, 255), 4)
    d.rectangle((ITEM_X - 22, ITEM_Y - 4, ITEM_X - 18, ITEM_Y + 2 * ITEM_STEP + 36), fill=ORANGE + (255,))
    for i in range(3):
        y = ITEM_Y + i * ITEM_STEP + 39
        d.line((ITEM_X, y, ITEM_X + 440, y), fill=(255, 255, 255, 22), width=1)

    # dicas de controle
    hint = text_font(17)
    x, y = 150, 672
    for glyph, label in (("A", "INICIAR"), ("+", "SAIR"), (None, "NAVEGAR")):
        cx, cy = x + 11, y + 11
        if glyph:
            d.ellipse((cx - 11, cy - 11, cx + 11, cy + 11), outline=(230, 230, 230, 255), width=2)
            gw = d.textlength(glyph, font=hint)
            d.text((cx - gw / 2, cy - 12), glyph, font=hint, fill=(230, 230, 230, 255))
        else:
            d.polygon(((cx, cy - 11), (cx - 7, cy - 3), (cx + 7, cy - 3)), fill=(230, 230, 230, 255))
            d.polygon(((cx, cy + 11), (cx - 7, cy + 3), (cx + 7, cy + 3)), fill=(230, 230, 230, 255))
        x = spaced(d, (x + 30, y + 1), label, hint, (190, 190, 190, 255), 2) + 34

    # moldura do botão de atualização (o texto é desenhado pelo launcher)
    d.rounded_rectangle((UPDATE_CX - 118, UPDATE_Y - 9, UPDATE_CX + 118, UPDATE_Y + UPDATE_H + 9),
                        radius=8, outline=(255, 255, 255, 60), width=2)
    return img.convert("RGB")


ITEM_H = 34  # altura do PNG do item; o espaçamento entre itens é 44


def make_item(text, sub=None, dim=False):
    fnt = font(TITLE_FONT, 38)
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    spacing = 3
    tw = spaced_width(probe, text, fnt, spacing)
    top, bottom = fnt.getbbox(text)[1], fnt.getbbox(text)[3]
    oy = (ITEM_H - 2 - (bottom - top)) // 2 - top  # maiúsculas centralizadas na altura do item
    sub_f = text_font(15, bold=False)
    sw = probe.textlength(sub, font=sub_f) + 16 if sub else 0
    img = Image.new("RGBA", (int(tw + sw + 4), ITEM_H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if not dim:
        spaced(d, (2, oy + 2), text, fnt, (0, 0, 0, 150), spacing)
    spaced(d, (0, oy), text, fnt, (98, 98, 98, 255) if dim else (242, 242, 242, 255), spacing)
    if sub:
        # alinhado pela base das maiúsculas do item
        sb = sub_f.getbbox(sub)
        d.text((tw + 14, oy + bottom - sb[3]), sub, font=sub_f, fill=(110, 110, 110, 255))
    return img


def png_bytes(img):
    out = io.BytesIO()
    img.save(out, "PNG", optimize=True)
    return out.getvalue()


# ---------------------------------------------------------------- romfs

def romfs_files(rom):
    """{nome: (offset da entrada na tabela de arquivos, offset dos dados, tamanho)} na raiz."""
    hdr = struct.unpack_from("<10Q", rom, 0)
    _, _, _, _, _, _, _, fm_off, fm_size, data_off = hdr
    files, pos = {}, 0
    while pos < fm_size:
        _, _, foff, fsize, _, nlen = struct.unpack_from("<IIQQII", rom, fm_off + pos)
        name = rom[fm_off + pos + 32:fm_off + pos + 32 + nlen].decode()
        files[name] = (pos, data_off + foff, fsize)
        pos += 32 + ((nlen + 3) & ~3)
    return hdr, files


def rebuild_romfs(rom, replace):
    """Mesmas tabelas (hash/metadados não dependem dos dados), dados realinhados."""
    hdr, files = romfs_files(rom)
    hsize, dh_off, dh_size, dm_off, dm_size, fh_off, fh_size, fm_off, fm_size, data_off = hdr
    tables_start = min(dh_off, dm_off, fh_off, fm_off)
    if tables_start < max(d + s for _, d, s in files.values()):
        raise SystemExit("layout de romfs inesperado")
    fmeta = bytearray(rom[fm_off:fm_off + fm_size])
    data = bytearray()
    for name, (meta, doff, size) in sorted(files.items(), key=lambda kv: kv[1][1]):
        blob = replace.get(name, bytes(rom[doff:doff + size]))
        data += b"\0" * ((-len(data)) % 16)
        struct.pack_into("<QQ", fmeta, meta + 8, len(data), len(blob))
        data += blob
    out = bytearray(rom[:data_off]) + data
    out += b"\0" * ((-len(out)) % 4)
    new_off = {}
    for key, off, size in (("dh", dh_off, dh_size), ("dm", dm_off, dm_size),
                           ("fh", fh_off, fh_size), ("fm", fm_off, fm_size)):
        new_off[key] = len(out)
        out += fmeta if key == "fm" else rom[off:off + size]
        out += b"\0" * ((-len(out)) % 4)
    struct.pack_into("<10Q", out, 0, hsize, new_off["dh"], dh_size, new_off["dm"], dm_size,
                     new_off["fh"], fh_size, new_off["fm"], fm_size, data_off)
    return bytes(out)


# ---------------------------------------------------------------- código do launcher

def movz_w(rd, imm):
    return 0x52800000 | (imm << 5) | rd


def add_w(rd, rn, imm):
    return 0x11000000 | (imm << 10) | (rn << 5) | rd


def patch_code(nro):
    """Desce o menu, move o botão de atualização (desenho, selecionado e toque) e troca o texto."""
    text_off, text_size = struct.unpack_from("<II", nro, 0x20)
    changes = []
    words = lambda w: [o for o in range(text_off, text_off + text_size, 4) if struct.unpack_from("<I", nro, o)[0] == w]

    # y do 1º item: add w7, w3, #286 (desenho) e add w1, w1, #286 (toque)
    for rd, rn, what in ((7, 3, "desenho"), (1, 1, "toque")):
        old, new = words(add_w(rd, rn, ITEM_Y_OLD)), words(add_w(rd, rn, ITEM_Y))
        if len(old) == 1:
            struct.pack_into("<I", nro, old[0], add_w(rd, rn, ITEM_Y))
            changes.append(f"menu em y={ITEM_Y} ({what}, +0x{old[0]:x})")
        elif not (len(old) == 0 and len(new) == 1):
            raise SystemExit(f"y do menu ({what}) encontrado {len(old)} vezes; versão não suportada")

    # centro x: "mov w0, #0x500; mov w1, #2" com "sdiv w0, w0, w1" logo depois
    centers = []
    for off in range(text_off, text_off + text_size - 20, 4):
        a, b = struct.unpack_from("<2I", nro, off)
        if a in (movz_w(0, 0x500), movz_w(0, UPDATE_CX * 2)) and b == 0x52800041 \
                and 0x1AC10C00 in struct.unpack_from("<4I", nro, off + 8):
            centers.append(off)
    if len(centers) != 2:
        raise SystemExit(f"centralização do botão de atualização encontrada {len(centers)} vezes; versão não suportada")
    for off in centers:
        if struct.unpack_from("<I", nro, off)[0] != movz_w(0, UPDATE_CX * 2):
            struct.pack_into("<I", nro, off, movz_w(0, UPDATE_CX * 2))
            changes.append(f"botão de atualização centralizado em x={UPDATE_CX} (+0x{off:x})")

    # y: mov w4, #0x15c (desenho normal e selecionado) e mov w1, #0x15c (toque)
    for rd, count in ((4, 2), (1, 1)):
        old, new = movz_w(rd, 0x15C), movz_w(rd, UPDATE_Y)
        sites = [o for o in range(text_off, text_off + text_size, 4) if struct.unpack_from("<I", nro, o)[0] == old]
        done = [o for o in range(text_off, text_off + text_size, 4) if struct.unpack_from("<I", nro, o)[0] == new]
        if len(sites) == count:
            for o in sites:
                struct.pack_into("<I", nro, o, new)
                changes.append(f"botão de atualização em y={UPDATE_Y} (+0x{o:x})")
        elif len(sites) != 0 or len(done) < count:
            raise SystemExit(f"y do botão de atualização (w{rd}) encontrado {len(sites)} vezes; versão não suportada")

    pos = nro.find(OLD_UPDATE_TEXT)
    if pos >= 0:
        nro[pos:pos + len(NEW_UPDATE_TEXT)] = NEW_UPDATE_TEXT
        changes.append(f"texto do botão: {NEW_UPDATE_TEXT[:-1].decode()}")
    elif nro.find(NEW_UPDATE_TEXT) < 0:
        raise SystemExit("texto CHECK FOR UPDATES não encontrado; versão não suportada")
    return changes


def main():
    if len(sys.argv) not in (2, 3):
        raise SystemExit(__doc__)
    src = sys.argv[1]
    dst = sys.argv[2] if len(sys.argv) == 3 else src
    nro = bytearray(open(src, "rb").read())
    if nro[0x10:0x14] != b"NRO0":
        raise SystemExit("não é um NRO")
    aset = struct.unpack_from("<I", nro, 0x18)[0]
    if nro[aset:aset + 4] != b"ASET":
        raise SystemExit("NRO sem ASET")
    icon_off, icon_size, nacp_off, nacp_size, rom_off, rom_size = struct.unpack_from("<6Q", nro, aset + 8)
    if aset + rom_off + rom_size != len(nro) or rom_off < max(icon_off + icon_size, nacp_off + nacp_size):
        raise SystemExit("o romfs não é a última parte do NRO; versão não suportada")
    rom = bytes(nro[aset + rom_off:])
    _, files = romfs_files(rom)
    for need in ("launcherBG.png", "startSP.png", "startMP.png", "startZM.png"):
        if need not in files:
            raise SystemExit(f"{need} não está no romfs; não parece o t6game.nro")

    _, doff, size = files["launcherBG.png"]
    orig = Image.open(io.BytesIO(rom[doff:doff + size]))
    if orig.info.get("Software") == MARKER:
        print("já está patchado; nada a fazer")
        return

    bg_info = PngInfo()
    bg_info.add_text("Software", MARKER)
    out = io.BytesIO()
    make_background(orig).save(out, "PNG", optimize=True, pnginfo=bg_info)
    replace = {
        "launcherBG.png": out.getvalue(),
        "startSP.png": png_bytes(make_item("CAMPANHA", sub="EM BREVE", dim=True)),
        "startMP.png": png_bytes(make_item("MULTIJOGADOR")),
        "startZM.png": png_bytes(make_item("ZUMBIS")),
    }
    new_rom = rebuild_romfs(rom, replace)
    nro = nro[:aset + rom_off] + new_rom
    struct.pack_into("<Q", nro, aset + 8 + 40, len(new_rom))

    changes = ["fundo e itens novos no romfs"] + patch_code(nro)
    write_nro(nro, src, dst, changes)


if __name__ == "__main__":
    main()
