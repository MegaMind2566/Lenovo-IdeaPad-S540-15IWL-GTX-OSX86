/* Execute the original registered OOM path; platform/identity endpoints are
 * the explicit fixtures used by the previously reviewed actual-body controls.
 * This callback test is functional evidence, not a callback stack/time bound. */
#define main retainedAllocatorFixtureMain
#include "../../prospective-allocator-stack-closure/tests/check_actual.c"
#undef main

static NvU32 reports;
static void report(void) { ++reports; }

int main(void)
{
    CHECK(portInitialize() == NV_OK);
    CHECK(portMemGlobals.pOomReportCb == NULL);
    portMemRegisterOomReportCb(report);
    CHECK(portMemGlobals.pOomReportCb == report);
    for (NvU32 i = 1; i <= 10; ++i) {
        NvLength large = ((NvLength)1) << (sizeof(NvLength) * 8 - 1);
        CHECK((i & 1 ? portMemAllocNonPaged(large) : portMemAllocPaged(large)) == NULL);
        CHECK(portMemGlobals.oomCount == i);
        CHECK(reports == (i == 10 ? 2 : 1));
    }
    portMemRegisterOomReportCb(NULL);
    CHECK(portMemGlobals.pOomReportCb == NULL);
    CHECK(portMemAllocNonPaged(((NvLength)1) << (sizeof(NvLength) * 8 - 1)) == NULL);
    CHECK(portMemGlobals.oomCount == 10 && reports == 2);
    void *a = portMemAllocNonPaged(23), *b = portMemAllocPaged(31);
    CHECK(a && b);
    CHECK(portMemGlobals.alloc.pagedImpl.tracking.counter.activeAllocs == 2);
    portMemFree(a); portMemFree(b);
    CHECK(portMemGlobals.alloc.pagedImpl.tracking.counter.activeAllocs == 0);
    printf("{\"checks\":%u,\"failures\":%u,\"oom_count\":%u,\"reports\":%u}\n",
        checks, failures, portMemGlobals.oomCount, reports);
    return failures ? 1 : 0;
}
