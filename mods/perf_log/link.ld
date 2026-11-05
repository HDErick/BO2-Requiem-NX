/* Blob único: tabela, entrada e o resto. O endereço é irrelevante (código PIC, -mcmodel=tiny). */
ENTRY(perf_frame)
SECTIONS
{
    . = 0x10000;
    .blob : {
        *(.text.tbl)
        *(.text.entry)
        *(.text .text.*)
        *(.rodata .rodata.*)
    }
    /DISCARD/ : { *(.comment) *(.note*) *(.eh_frame*) *(.data*) *(.bss*) }
}
