#!/bin/sh
# Rebuilds cfg_buf.bin. Needs zig: on PATH, or ZIG="python3 -m ziglang" (pip install ziglang).
set -e
cd "$(dirname "$0")"
ZIG="${ZIG:-zig}"
$ZIG cc -target aarch64-freestanding-none -Os -mcmodel=tiny -ffixed-x18 -fno-omit-frame-pointer \
    -ffreestanding -fno-builtin -fno-stack-protector -fno-unwind-tables -fno-asynchronous-unwind-tables \
    -nostdlib -static -Wl,-T,link.ld -Wl,--gc-sections -Wl,-e,cfg_slots -o cfg_buf.elf cfg_buf.c
$ZIG objcopy -O binary --only-section=.blob cfg_buf.elf cfg_buf.bin
rm -f cfg_buf.elf
