#!/usr/bin/env python3
"""Builds the launcher romfs from the original t6game.nro.

  romfs/bg.png       1280x720 background: texture and R logo from the original launcherBG.png,
                     darkened left side, glow behind the logo, title and footer band
  romfs/title.ttf    font for titles and menu items (DIN Condensed Bold on macOS)
  romfs/text.ttf     font for smaller text (Avenir Next Condensed on macOS; a .ttc works)
  romfs/text.idx     indices of the regular and bold faces inside text.ttf
  romfs/nav.pcm      navigation sound: the original UInavigate.mp3 as 48 kHz 16-bit stereo PCM
                     (needs ffmpeg or macOS afconvert; skipped with a warning without them)
  icon.jpg           icon of the original NRO

None of this goes into the repository: the background and icon belong to the port, and
the fonts belong to the system. Other fonts: LAUNCHER_TITLE_FONT / LAUNCHER_TEXT_FONT
(.ttf or .ttc), LAUNCHER_TEXT_FONT_INDEX and LAUNCHER_TEXT_FONT_BOLD_INDEX.

Usage: python3 make_assets.py path/to/t6game.nro output_dir
"""
import io
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import wave

from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 1280, 720
X0, HEADER_Y = 110, 134          # must match the layout in source/main.c
ORANGE = (255, 122, 0)
TITLE_FONT = os.environ.get("LAUNCHER_TITLE_FONT", "/System/Library/Fonts/Supplemental/DIN Condensed Bold.ttf")
TEXT_FONT = os.environ.get("LAUNCHER_TEXT_FONT", "/System/Library/Fonts/Avenir Next Condensed.ttc")
TEXT_FONT_INDEX = int(os.environ.get("LAUNCHER_TEXT_FONT_INDEX", "5"))       # Medium in the macOS .ttc
TEXT_FONT_BOLD_INDEX = int(os.environ.get("LAUNCHER_TEXT_FONT_BOLD_INDEX", "0"))  # Bold


def nro_assets(path):
    """(JPEG icon, launcherBG.png, UInavigate.mp3 or None) from the original NRO."""
    nro = open(path, "rb").read()
    if nro[0x10:0x14] != b"NRO0":
        raise SystemExit("not an NRO")
    aset = struct.unpack_from("<I", nro, 0x18)[0]
    if nro[aset:aset + 4] != b"ASET":
        raise SystemExit("NRO has no ASET section")
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
        raise SystemExit("launcherBG.png is not in the romfs; this does not look like the original t6game.nro")
    return nro[aset + icon_off:aset + icon_off + icon_size], files["launcherBG.png"], files.get("UInavigate.mp3")


def pcm_48k_stereo(mp3):
    """Raw 48 kHz s16le stereo PCM (what audout plays), or None without a converter."""
    with tempfile.TemporaryDirectory() as tmp:
        src, dst = os.path.join(tmp, "in.mp3"), os.path.join(tmp, "out.wav")
        open(src, "wb").write(mp3)
        if shutil.which("ffmpeg"):
            cmd = ["ffmpeg", "-loglevel", "error", "-i", src, "-ar", "48000", "-ac", "2", "-c:a", "pcm_s16le", dst]
        elif shutil.which("afconvert"):
            cmd = ["afconvert", "-f", "WAVE", "-d", "LEI16@48000", "-c", "2", src, dst]
        else:
            return None
        subprocess.run(cmd, check=True)
        with wave.open(dst) as w:
            if (w.getframerate(), w.getnchannels(), w.getsampwidth()) != (48000, 2, 2):
                raise SystemExit("unexpected format from the audio converter")
            return w.readframes(w.getnframes())


def spaced(draw, xy, text, fnt, fill, spacing):
    x, y = xy
    for ch in text:
        draw.text((x, y), ch, font=fnt, fill=fill)
        x += draw.textlength(ch, font=fnt) + spacing
    return x


def make_background(orig):
    img = orig.convert("RGB").resize((W, H)).convert("RGBA")

    # darken the left side for the text; the logo on the right stays visible
    shade = Image.new("L", (W, H))
    shade.putdata([int(235 * (max(0.0, 1.0 - x / 820.0) ** 1.4)) for _ in range(H) for x in range(W)])
    img = Image.composite(Image.new("RGBA", (W, H), (6, 7, 9, 255)), img, shade)

    # orange glow behind the logo
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse((800, 120, 1180, 580), fill=ORANGE + (70,))
    img = Image.alpha_composite(img, glow.filter(ImageFilter.GaussianBlur(90)))

    # vignette at the top and dark band at the bottom
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
    icon, bg, nav = nro_assets(sys.argv[1])
    out = sys.argv[2]
    os.makedirs(os.path.join(out, "romfs"), exist_ok=True)
    make_background(Image.open(io.BytesIO(bg))).save(os.path.join(out, "romfs", "bg.png"), optimize=True)
    open(os.path.join(out, "icon.jpg"), "wb").write(icon)
    open(os.path.join(out, "romfs", "title.ttf"), "wb").write(open(TITLE_FONT, "rb").read())
    open(os.path.join(out, "romfs", "text.ttf"), "wb").write(open(TEXT_FONT, "rb").read())
    open(os.path.join(out, "romfs", "text.idx"), "w").write(f"{TEXT_FONT_INDEX} {TEXT_FONT_BOLD_INDEX}\n")
    pcm = pcm_48k_stereo(nav) if nav else None
    if pcm:
        open(os.path.join(out, "romfs", "nav.pcm"), "wb").write(pcm)
    else:
        print("warning: no navigation sound (UInavigate.mp3 missing, or neither ffmpeg nor afconvert found)")
    print(f"assets in {out}")


if __name__ == "__main__":
    main()
