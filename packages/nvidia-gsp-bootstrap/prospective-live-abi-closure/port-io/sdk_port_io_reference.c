/* SPDX-License-Identifier: MIT */
/* Independent typed wrappers for the actual pinned SDK port operations. */
#include "nv.h"
#include "os-interface.h"
#include <architecture/i386/pio.h>

NvU8 s540SdkPortReadByte(NvU32 address) { return inb((i386_ioport_t)address); }
NvU16 s540SdkPortReadWord(NvU32 address) { return inw((i386_ioport_t)address); }
NvU32 s540SdkPortReadDword(NvU32 address) { return inl((i386_ioport_t)address); }
void s540SdkPortWriteByte(NvU32 address, NvU8 value) { outb((i386_ioport_t)address, value); }
void s540SdkPortWriteWord(NvU32 address, NvU16 value) { outw((i386_ioport_t)address, value); }
void s540SdkPortWriteDword(NvU32 address, NvU32 value) { outl((i386_ioport_t)address, value); }

_Static_assert(__builtin_types_compatible_p(__typeof__(&os_io_read_byte), NvU8 (*)(NvU32)), "Read8 ABI");
_Static_assert(__builtin_types_compatible_p(__typeof__(&os_io_read_word), NvU16 (*)(NvU32)), "Read16 ABI");
_Static_assert(__builtin_types_compatible_p(__typeof__(&os_io_read_dword), NvU32 (*)(NvU32)), "Read32 ABI");
_Static_assert(__builtin_types_compatible_p(__typeof__(&os_io_write_byte), void (*)(NvU32, NvU8)), "Write8 ABI");
_Static_assert(__builtin_types_compatible_p(__typeof__(&os_io_write_word), void (*)(NvU32, NvU16)), "Write16 ABI");
_Static_assert(__builtin_types_compatible_p(__typeof__(&os_io_write_dword), void (*)(NvU32, NvU32)), "Write32 ABI");
