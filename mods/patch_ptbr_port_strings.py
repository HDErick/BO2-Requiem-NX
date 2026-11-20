#!/usr/bin/env python3
"""Brazilian Portuguese for the menu texts the Requiem NX port added (t6mp.nro and t6zm.nro).

The port's own options are not in the game's localizedstrings, so the official PT-BR
localization (see "PT-BR menus" in README.md) leaves them in English. This patch
rewrites them in Portuguese, in two places of t6*_guest.elf:

- Native strings: Controls > Gamepad AIM ASSIST, GYRO AIMING, AUTO RUN, RESPONSE CURVE
  and the ADS sliders, and the DEADZONES sliders (labels, descriptions and choices).
  The code pushes them to Lua with lua_pushstring (strlen), from adrp+add or from
  option tables whose pointers carry R_AARCH64_P32_RELATIVE relocations. Each
  translation goes in place, NUL-padded, when it fits in the string plus its alignment
  padding (nothing points inside these strings). A table entry that does not fit (or
  "ENABLED", which is the tail of another string) is written after the end of a
  shortened translation and its pointer (relocation addend and stored value) moved there.
- The embedded Lua source registered as ui_mp/t6/nxcontrols.lua (Settings > MAIN MENU
  with its restart popup, SENSITIVITY HORIZONTAL / VERTICAL, the DEADZONES tab). The
  loader takes it by pointer and measures it with strlen, so the chunk is rewritten at
  the same size: comments and trailing blanks stripped (every line keeps its number), the
  visible strings translated, spaces as padding. Log messages stay in English.

No code changes and nothing grows. The texts are always Portuguese after the patch (the
port keeps the game in English and the PT-BR pack replaces the English strings, so there
is no language to follow): apply it only if you use the PT-BR localization.

Usage: python3 patch_ptbr_port_strings.py path/to/t6mp.nro|t6zm.nro [output.nro]
Without [output.nro], overwrites in place and keeps a .bak of the original.
"""
import re
import struct
import sys

from nro_guest import Guest, find_guest, write_nro

P32_RELATIVE = 183

# Strings the native code addresses with adrp+add: translated in place only.
CODE = [
    ("AIM ASSIST", "MIRA ASSISTIDA"),
    ("Enable or disable gamepad aim slowdown, ADS auto-aim and target tracking.",
     "Ativa/desativa a mira lenta no alvo, a auto-mira no ADS e o rastreio de alvos."),
    ("Horizontal look speed while aiming down the sights, times the horizontal sensitivity."
     " 1.00 = the game's own.",
     "Velocidade horizontal da visão ao mirar (ADS), vezes a sensibilidade horizontal."
     " 1.00 = a do jogo."),
    ("Vertical look speed while aiming down the sights, times the vertical sensitivity."
     " 1.00 = the game's own.",
     "Velocidade vertical da visão ao mirar (ADS), vezes a sensibilidade vertical."
     " 1.00 = a do jogo."),
]

DEADZONE_ROWS = [
    ("gpad_lstick_deadzone_inner", "Left Analog Start", "Analógico esq. início",
     "Left stick dead zone START: % of the travel ignored around the centre. 0 = none, every"
     " touch counts; raise it if the stick drifts. Default: 20.",
     "Zona morta do analógico esq., INÍCIO: % do curso ignorada no centro. 0 = nenhuma, todo"
     " toque conta; aumente se houver drift. Padrão: 20."),
    ("gpad_lstick_deadzone_outer", "Left Analog End", "Analógico esq. fim",
     "Left stick dead zone END: % before the edge where the stick already counts as fully"
     " pushed. 0 = only at the very edge. Default: 1.",
     "Zona morta do analógico esq., FIM: % antes da borda em que o analógico já conta como"
     " todo empurrado. 0 = só no limite. Padrão: 1."),
    ("gpad_rstick_deadzone_inner", "Right Analog Start", "Analógico dir. início",
     "Right stick dead zone START: % of the travel ignored around the centre. 0 = none, every"
     " touch counts; raise it if the stick drifts. Default: 20.",
     "Zona morta do analógico dir., INÍCIO: % do curso ignorada no centro. 0 = nenhuma, todo"
     " toque conta; aumente se houver drift. Padrão: 20."),
    ("gpad_rstick_deadzone_outer", "Right Analog End", "Analógico dir. fim",
     "Right stick dead zone END: % before the edge where the stick already counts as fully"
     " pushed. 0 = only at the very edge. Default: 1.",
     "Zona morta do analógico dir., FIM: % antes da borda em que o analógico já conta como"
     " todo empurrado. 0 = só no limite. Padrão: 1."),
    ("gpad_ltrigger_deadzone_inner", "Left Trigger Start", "Gatilho esq. início",
     "Left trigger dead zone START: % of the pull ignored before it registers. 0 = the"
     " lightest touch counts. Default: 13.",
     "Zona morta do gatilho esq., INÍCIO: % do aperto ignorada antes de registrar. 0 = o"
     " toque mais leve conta. Padrão: 13."),
    ("gpad_ltrigger_deadzone_outer", "Left Trigger End", "Gatilho esq. fim",
     "Left trigger dead zone END: % before the end of the pull where it already counts as"
     " fully pressed. 0 = only fully pulled. Default: 0.",
     "Zona morta do gatilho esq., FIM: % antes do fim do aperto em que já conta como todo"
     " apertado. 0 = só no fim. Padrão: 0."),
    ("gpad_rtrigger_deadzone_inner", "Right Trigger Start", "Gatilho dir. início",
     "Right trigger dead zone START: % of the pull ignored before it registers. 0 = the"
     " lightest touch counts. Default: 13.",
     "Zona morta do gatilho dir., INÍCIO: % do aperto ignorada antes de registrar. 0 = o"
     " toque mais leve conta. Padrão: 13."),
    ("gpad_rtrigger_deadzone_outer", "Right Trigger End", "Gatilho dir. fim",
     "Right trigger dead zone END: % before the end of the pull where it already counts as"
     " fully pressed. 0 = only fully pulled. Default: 0.",
     "Zona morta do gatilho dir., FIM: % antes do fim do aperto em que já conta como todo"
     " apertado. 0 = só no fim. Padrão: 0."),
]

# Option tables of pointers (label, dvar, description, choices...), found from the dvar
# pointer: (dvar, [(byte offset from the dvar pointer, English, Portuguese), ...]).
TABLES = [
    ("gpad_gyro_enabled", [
        (-4, "GYRO AIMING", "GIROSCÓPIO"),
        (4, "Aim by moving your controller or console. Works alongside the right stick during"
            " gameplay. Default: DISABLED. Aim-Only activates motion while aiming down sights.",
            "Mire movendo o controle ou o console. Funciona junto com o analógico direito"
            " durante o jogo. Padrão: DESABILITADO. Só ao mirar: ativa o movimento apenas no ADS."),
        (8, "DISABLED", "DESABILITADO"),
        (12, "Always On", "Sempre ativo"),
        (16, "Aim-Only", "Só ao mirar"),
    ]),
    ("gpad_autorun", [
        (-4, "AUTO RUN", "CORRIDA AUTOMÁTICA"),
        (4, "Sprint automatically when the left stick is pushed forward, without clicking it."
            " Not while aiming down sights, crouched or prone. Default: DISABLED.",
            "Corre sozinho ao empurrar o analógico esquerdo para frente, sem clicá-lo. Não"
            " funciona mirando, agachado ou debruçado. Padrão: DESABILITADO."),
        (8, "DISABLED", "DESABILITADO"),
        (12, "ENABLED", "HABILITADO"),
    ]),
    ("gpad_response_curve", [
        (-4, "RESPONSE CURVE", "CURVA DE RESPOSTA"),
        (4, "How the right stick turns into look speed. Standard: the original Black Ops II"
            " curve. Linear: speed follows the stick exactly. Quadratic: a gentler, curved start"
            " that becomes linear, so touching the stick is not abrupt. Dynamic: an S curve, slow"
            " and precise near the centre, fast towards the edge. Default: STANDARD.",
            "Como o analógico direito vira velocidade da visão. Original: a curva do Black Ops"
            " II. Linear: segue o analógico à risca. Quadrática: começo suave que vira linear, sem"
            " trancos. Dinâmica: curva em S, precisa no centro, rápida na borda. Padrão: ORIGINAL."),
        (8, "STANDARD", "ORIGINAL"),
        (16, "QUADRATIC", "QUADRÁTICA"),     # +12 is LINEAR, the same in Portuguese
        (20, "DYNAMIC", "DINÂMICA"),
    ]),
] + [(dvar, [(-4, label_en, label_pt), (4, hint_en, hint_pt)])
     for dvar, label_en, label_pt, hint_en, hint_pt in DEADZONE_ROWS]

# Lua chunk ui_mp/t6/nxcontrols.lua: start of the source and its visible string literals.
LUA_START = b"local nxSwitch = true\n"
LUA = [
    ("MAIN MENU", "MENU PRINCIPAL"),
    ("The look of the main menu. Modern: the list on the right with descriptions and the globe"
     " on display. Classic: the original Black Ops II menu. Applied when the game restarts:"
     " leaving Settings offers it. Default: MODERN.",
     "O visual do menu principal. Moderno: a lista à direita com descrições e o globo em"
     " destaque. Clássico: o menu original do Black Ops II. Aplicado ao reiniciar o jogo"
     " (oferecido ao sair das Configurações). Padrão: MODERNO."),
    ("CLASSIC", "CLÁSSICO"),
    ("MODERN", "MODERNO"),
    ("RESTART REQUIRED", "REINÍCIO NECESSÁRIO"),
    ("The main menu style is saved.", "O estilo do menu principal foi salvo."),
    ("Restart the game now to apply it?", "Reiniciar o jogo agora para aplicá-lo?"),
    ("RESTART NOW", "REINICIAR AGORA"),
    ("Restarting...", "Reiniciando..."),
    ("LATER", "DEPOIS"),
    ("SENSITIVITY HORIZONTAL", "SENSIBILIDADE HORIZONTAL"),
    ("How fast the right stick turns the view left and right (the LOOK SENSITIVITY scale).",
     "A rapidez com que o analógico direito gira a visão para os lados (escala da"
     " SENSIBILIDADE DA VISTA)."),
    ("SENSITIVITY VERTICAL", "SENSIBILIDADE VERTICAL"),
    ("How fast the right stick turns the view up and down (the LOOK SENSITIVITY scale).",
     "A rapidez com que o analógico direito gira a visão para cima e para baixo (escala da"
     " SENSIBILIDADE DA VISTA)."),
    ("DEADZONES", "ZONAS MORTAS"),
]


def rodata(g):
    addr, off, _ = g.secs[".rodata"]
    return addr, g.start + off, g.start + off + g.secs[".rodata"][2]


def find_cstrings(g, s):
    """VAs of every NUL-delimited copy of the string in .rodata."""
    addr, lo, hi = rodata(g)
    needle = b"\0" + s + b"\0"
    out, at = [], lo - 1
    while (at := g.nro.find(needle, at + 1, hi)) >= 0:
        out.append(addr + at + 1 - lo)
    return out


def cstring(g, va):
    off = g.va_to_off(va)
    return bytes(g.nro[off:g.nro.index(b"\0", off)])


def pointed_text(g, rels, r_off):
    """The string a relocated pointer points at in .rodata, or None."""
    if r_off not in rels:
        return None
    addr, _, size = g.secs[".rodata"]
    va = rels[r_off][1]
    return cstring(g, va) if addr <= va < addr + size else None


def relocations(g):
    """{r_offset: (NRO offset of the Elf32_Rela, addend)} of the P32_RELATIVE relocations."""
    _, off, size = g.secs[".rela.dyn"]
    out = {}
    for pos in range(g.start + off, g.start + off + size, 12):
        r_off, info, addend = struct.unpack_from("<IIi", g.nro, pos)
        if info == P32_RELATIVE:
            out[r_off] = (pos, addend)
    return out


class Slot:
    """A string the patch translates and who points at it (code, or relocated pointers)."""

    def __init__(self, en, pt, va, state, fields):
        self.en, self.pt, self.va, self.state, self.fields = en, pt, va, state, fields


def native_slots(g, rels):
    by_addend = {}
    for r_off, (_, addend) in rels.items():
        by_addend.setdefault(addend, []).append(r_off)
    slots = []
    for en, pt in CODE:
        en_b, pt_b = en.encode(), pt.encode()
        hits = [(va, "en") for va in find_cstrings(g, en_b)] + [(va, "pt") for va in find_cstrings(g, pt_b)]
        if len(hits) != 1:
            raise SystemExit(f"{en!r} found {len(hits)} times; unsupported version")
        slots.append(Slot(en_b, pt_b, hits[0][0], hits[0][1], None))
    for dvar, fields in TABLES:
        dvar_vas = find_cstrings(g, dvar.encode())
        rows = [r for va in dvar_vas for r in by_addend.get(va, [])
                if all(pointed_text(g, rels, r + delta) in (en.encode(), pt.encode())
                       for delta, en, pt in fields)]
        if len(rows) != 1:
            raise SystemExit(f"option table of {dvar} found {len(rows)} times; unsupported version")
        for delta, en, pt in fields:
            r_off = rows[0] + delta
            va = rels[r_off][1]
            text = cstring(g, va)
            state = "en" if text == en.encode() else "pt"
            slots.append(Slot(en.encode(), pt.encode(), va, state, [r_off]))
    return slots


def lua_chunk(g):
    """(NRO offset, source) of the nxcontrols.lua chunk."""
    _, lo, hi = rodata(g)
    at = g.nro.find(b"\0" + LUA_START, lo, hi)
    if at < 0 or g.nro.find(b"\0" + LUA_START, at + 1, hi) >= 0:
        raise SystemExit("nxcontrols.lua source not found once; unsupported version")
    start = at + 1
    src = bytes(g.nro[start:g.nro.index(b"\0", start)])
    if b"Engine.NXAddDeadzoneSliders(list)" not in src:
        raise SystemExit("unexpected nxcontrols.lua source; unsupported version")
    return start, src


def strip_lua_comments(src):
    """The source without comments and trailing blanks, on the same lines (strings, which
    here never span lines, are kept as is)."""
    out, i, n = [], 0, len(src)
    while i < n:
        c = src[i]
        if c in "\"'":
            j = i + 1
            while src[j] != c:
                if src[j] == "\\":
                    j += 1
                if src[j] == "\n":
                    raise SystemExit("multi-line string in nxcontrols.lua; unsupported version")
                j += 1
            out.append(src[i:j + 1])
            i = j + 1
        elif src.startswith("--", i):
            if re.match(r"--\[=*\[", src[i:i + 8]):
                raise SystemExit("block comment in nxcontrols.lua; unsupported version")
            j = src.find("\n", i)
            i = n if j < 0 else j
        elif c == "[" and re.match(r"\[=*\[", src[i:i + 8]):
            raise SystemExit("long string in nxcontrols.lua; unsupported version")
        else:
            out.append(c)
            i += 1
    return "\n".join(line.rstrip() for line in "".join(out).split("\n"))


def lua_state(src):
    text = src.decode()
    en = [text.count(f'"{e}"') for e, _ in LUA]
    pt = [text.count(f'"{p}"') for _, p in LUA]
    if all(c == 1 for c in en) and not any(pt):
        return "en"
    if all(c == 1 for c in pt) and not any(en):
        return "pt"
    raise SystemExit("nxcontrols.lua strings neither all English nor all Portuguese; unsupported version")


def translate_lua(src):
    code = strip_lua_comments(src.decode())
    for en, pt in LUA:
        code = code.replace(f'"{en}"', f'"{pt}"')
    out = code.encode()
    if len(out) > len(src):
        raise SystemExit("translated nxcontrols.lua does not fit")
    return out + b" " * (len(src) - len(out))


def slot_end(g, off):
    """NRO offset of the first non-zero byte after the string at `off`."""
    end = g.nro.index(b"\0", off)
    while g.nro[end] == 0:
        end += 1
    return end


def patch_native(g, slots, rels, changes):
    unique = {}
    for s in slots:
        if s.va in unique:
            unique[s.va].fields += s.fields      # DISABLED is shared by two tables
        else:
            unique[s.va] = Slot(s.en, s.pt, s.va, s.state, None if s.fields is None else list(s.fields))
    in_place, moved, hosts = [], [], []
    for s in unique.values():
        off = g.va_to_off(s.va)
        end = slot_end(g, off)
        if g.nro[off - 1] == 0 and len(s.pt) < end - off:
            in_place.append((s, off, end))
        elif s.fields:
            moved.append(s)
        else:
            raise SystemExit(f"{s.pt!r} does not fit in place")
    for s, off, end in in_place:
        g.nro[off:off + len(s.en)] = bytes(len(s.en))
        g.nro[off:off + len(s.pt)] = s.pt
        hosts.append([off + len(s.pt) + 1, end])
        changes.append(f"  {short(s.en.decode())} -> {short(s.pt.decode())}")
    hosts.sort()
    # Longer texts after the end of shortened ones, first fit; the bytes there are free
    # (nothing points inside these strings) and stay NUL-terminated.
    for s in sorted(moved, key=lambda s: -len(s.pt)):
        host = next((h for h in hosts if h[1] - h[0] >= len(s.pt) + 1), None)
        if host is None:
            raise SystemExit("no room for the translations that do not fit in place")
        off = host[0]
        g.nro[off:off + len(s.pt)] = s.pt
        host[0] += len(s.pt) + 1
        va = s.va + (off - g.va_to_off(s.va))
        for r_off in s.fields:
            pos, _ = rels[r_off]
            struct.pack_into("<i", g.nro, pos + 8, va)
            g.put(g.va_to_off(r_off), va)
        changes.append(f"  {short(s.en.decode())} -> {short(s.pt.decode())} (pointer moved to 0x{va:x})")


def short(text):
    return repr(text if len(text) <= 48 else text[:45] + "...")


def main():
    if len(sys.argv) not in (2, 3):
        raise SystemExit(__doc__)
    src = sys.argv[1]
    dst = sys.argv[2] if len(sys.argv) == 3 else src
    nro = bytearray(open(src, "rb").read())
    name, start = find_guest(nro)
    g = Guest(nro, start)

    rels = relocations(g)
    slots = native_slots(g, rels)
    lua_off, lua_src = lua_chunk(g)
    states = {s.state for s in slots} | {lua_state(lua_src)}
    changes = []
    if states == {"en"}:
        changes.append(f"{name}: port menu texts in PT-BR")
        patch_native(g, slots, rels, changes)
        nro[lua_off:lua_off + len(lua_src)] = translate_lua(lua_src)
        changes += [f"  nxcontrols.lua: {short(en)} -> {short(pt)}" for en, pt in LUA]
    elif states != {"pt"}:
        raise SystemExit("port menu texts partly translated; unsupported version")
    write_nro(nro, src, dst, changes)


if __name__ == "__main__":
    main()
