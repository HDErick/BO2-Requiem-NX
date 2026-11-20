/* Single blob: table, entry point, then the rest. The address does not matter (PIC code, -mcmodel=tiny). */
ENTRY(aa_entry)
SECTIONS
{
    . = 0x10000;
    .blob : {
        *(.text.tbl)
        *(.text.slots)
        *(.text.entry)
        *(.text .text.*)
        *(.rodata .rodata.*)
    }
    /DISCARD/ : { *(.comment) *(.note*) *(.eh_frame*) *(.data*) *(.bss*) }
}
