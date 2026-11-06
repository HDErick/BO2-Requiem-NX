#!/bin/sh
# Builds the new launcher: build.sh path/to/t6game.nro.original [output.nro]
#
# Generates the assets from the original launcher (needs Python with Pillow; PYTHON=...)
# and compiles inside the devkitpro/devkita64 container (docker). The Mods screen
# carries perf_log.bin, aim_gate.bin and aim_assist_bots_only.gsc in its romfs.
set -e
cd "$(dirname "$0")"
ORIG="$1"
OUT="${2:-launcher.nro}"
[ -f "$ORIG" ] || { echo "usage: $0 t6game.nro.original [output.nro]"; exit 1; }
PYTHON="${PYTHON:-python3}"

rm -rf assets
$PYTHON make_assets.py "$ORIG" assets
cp ../perf_log/perf_log.bin ../aim_gate/aim_gate.bin \
   ../sd/switch/t6game/scripts/mp/aim_assist_bots_only.gsc assets/romfs/
docker run --rm --platform linux/amd64 -v "$PWD":/src -w /src devkitpro/devkita64 \
    sh -c 'make clean >/dev/null && make -j4 ASSETS=assets'
[ "$OUT" = launcher.nro ] || cp launcher.nro "$OUT"
echo "-> $OUT"
