#!/bin/sh
# Compila o launcher novo: build.sh caminho/para/t6game.nro.original [saida.nro]
#
# Gera os assets a partir do launcher original (precisa de Python com Pillow; PYTHON=...)
# e compila com o container devkitpro/devkita64 (docker).
set -e
cd "$(dirname "$0")"
ORIG="$1"
OUT="${2:-launcher.nro}"
[ -f "$ORIG" ] || { echo "uso: $0 t6game.nro.original [saida.nro]"; exit 1; }
PYTHON="${PYTHON:-python3}"

rm -rf assets
$PYTHON make_assets.py "$ORIG" assets
docker run --rm --platform linux/amd64 -v "$PWD":/src -w /src devkitpro/devkita64 \
    sh -c 'make clean >/dev/null && make -j4 ASSETS=assets'
[ "$OUT" = launcher.nro ] || cp launcher.nro "$OUT"
echo "-> $OUT"
