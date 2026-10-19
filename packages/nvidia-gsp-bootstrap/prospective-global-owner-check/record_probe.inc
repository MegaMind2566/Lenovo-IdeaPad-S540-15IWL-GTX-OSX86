/* CPU-only readback of the actual strong record; no state is changed. */
#if defined(KERNEL)
#error "The global-owner CPU readback probe must never enter a kernel image"
#endif
#include "Probe.h"
void s540GlobalOwnerCheckProbe(S540GlobalOwnerCheckProbe *out)
{
    NvU32 i; NvU64 control;
    if (!out) return;
    *out = (S540GlobalOwnerCheckProbe){0};
    control = LD(&record.control);
    out->generation = LD(&record.generation);
    out->masterThread = LD(&record.masterThread);
    out->owner = LD(&record.owner);
    out->nv = LD(&record.nv);
    out->phase = (NvU32)control ? S540_FIRST_RETAINED : LD(&record.phase);
    out->firstStatus = (NvU32)control;
    out->firstSite = (NvU32)((control >> 32) & 0xffffU);
    out->inFlightFreePermits = (NvU32)(control >> 48);
    for (i = 0; i < CAPACITY; ++i)
        if (LD(&unknownObjects[i])) ++out->unknownRetainedObjects;
}
