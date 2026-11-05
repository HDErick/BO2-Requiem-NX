#!/bin/sh
# Recompila perf_log.bin. Precisa do zig: no PATH, ou ZIG="python3 -m ziglang" (pip install ziglang).
set -e
cd "$(dirname "$0")"
ZIG="${ZIG:-zig}"
$ZIG cc -target aarch64-freestanding-none -Os -mcmodel=tiny -ffixed-x18 -fno-omit-frame-pointer \
    -ffreestanding -fno-builtin -fno-stack-protector -fno-unwind-tables -fno-asynchronous-unwind-tables \
    -nostdlib -static -Wl,-T,link.ld -Wl,--gc-sections -Wl,-e,perf_frame -o perf_log.elf perf_log.c
$ZIG objcopy -O binary --only-section=.blob perf_log.elf perf_log.bin
rm -f perf_log.elf
