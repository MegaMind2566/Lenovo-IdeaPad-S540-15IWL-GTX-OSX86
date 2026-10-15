// SPDX-License-Identifier: MIT
// Native user-space test fixture ONLY. Production compiles the unmodified
// upstream arch/nvalloc/unix/src/asm/x86/nv_rdcr.c, which actually reads CR4.
// The original exact NvU32 ABI is preserved. A zero fixture deliberately does
// not advertise OSFXSR/OSXSAVE support; it is not a host CPU-state measurement.
#ifdef KERNEL
#error "The privileged CPU test fixture must never enter a kernel build"
#endif
#include "os/os.h"
NvU32 osNv_rdcr4(void)
{
    return 0;
}
