#!/bin/sh
# Rebuilds aim_gate.bin. Needs zig: on PATH, or ZIG="python3 -m ziglang" (pip install ziglang).
set -e
cd "$(dirname "$0")"
ZIG="${ZIG:-zig}"
$ZIG cc -target aarch64-freestanding-none -Os -mcmodel=tiny -ffixed-x18 -fno-omit-frame-pointer \
    -ffreestanding -fno-builtin -fno-stack-protector -fno-unwind-tables -fno-asynchronous-unwind-tables \
    -nostdlib -static -Wl,-T,link.ld -Wl,--gc-sections -Wl,-e,aa_entry -o aim_gate.elf aim_gate.c
$ZIG objcopy -O binary --only-section=.blob aim_gate.elf aim_gate.bin
rm -f aim_gate.elf
