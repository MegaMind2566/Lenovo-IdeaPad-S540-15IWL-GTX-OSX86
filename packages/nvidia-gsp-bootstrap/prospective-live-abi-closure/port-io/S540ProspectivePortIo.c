/* SPDX-License-Identifier: MIT */
/* Actual x86 port instructions through the pinned Apple SDK interface. */
#include "nv.h"
#include "os-interface.h"
#include <architecture/i386/pio.h>

#if !defined(S540_NVIDIA_DARWIN_PORT_IO) || S540_NVIDIA_DARWIN_PORT_IO != 1
#error "Explicit selected Darwin port-I/O source profile required"
#endif
#if !defined(KERNEL) || !defined(__KERNEL__) || !defined(NV_X86_64) || !defined(NV_UNIX) || NV_ARCH_BITS != 64
#error "Port-I/O callbacks require the exact x86-64 Unix kernel ABI"
#endif
#if !defined(os_io_read_byte) || !defined(os_io_write_dword)
#error "Port-I/O callbacks require the actual private original namespace"
#endif

NvU8 NV_API_CALL os_io_read_byte(NvU32 address)
{
    return inb((i386_ioport_t)address);
}
NvU16 NV_API_CALL os_io_read_word(NvU32 address)
{
    return inw((i386_ioport_t)address);
}
NvU32 NV_API_CALL os_io_read_dword(NvU32 address)
{
    return inl((i386_ioport_t)address);
}
void NV_API_CALL os_io_write_byte(NvU32 address, NvU8 value)
{
    outb((i386_ioport_t)address, value);
}
void NV_API_CALL os_io_write_word(NvU32 address, NvU16 value)
{
    outw((i386_ioport_t)address, value);
}
void NV_API_CALL os_io_write_dword(NvU32 address, NvU32 value)
{
    outl((i386_ioport_t)address, value);
}
