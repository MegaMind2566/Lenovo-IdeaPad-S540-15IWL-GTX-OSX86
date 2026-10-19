/* SPDX-License-Identifier: MIT */
/* Actual original types and complete extracted bodies. Explicit fixtures are
 * only contention/read/copy/print endpoints; none attests hardware ownership. */
#include "nv.h"
#include "gpu/gpu.h"
#include "gpu/gsp/kernel_gsp.h"
#include "S540NvidiaGspCancellation.h"
#include "S540NvidiaDarwinServices.h"

static KernelGsp gsp;
static LIBOS_LOG_DECODE decoder;
static libosLogMetadata metadata;
static NvU64 scratch[256], merged[2048], physical[513];
static NvU32 entered, released, reads, copies, prints, logs, nvlogs;
static NvU32 blockRead, blockCopy, blockSpin, blockDump, completeAfter;
static NvU64 mergedEntries;
static void block_endpoint(void) {
    __atomic_store_n(&entered, 1U, __ATOMIC_RELEASE);
    while (!__atomic_load_n(&released, __ATOMIC_ACQUIRE)) {}
}
static void fixtureSpin(void) {
    ++reads;
    if (blockSpin && reads == 1) block_endpoint();
    if (reads == 8) __c11_atomic_store(&gsp.logDumpLock, 0, __ATOMIC_RELEASE);
}
static void fixtureDump(KernelGsp *which, NvBool sync) {
    (void)which; (void)sync; ++logs;
    if (blockDump) block_endpoint();
}
static void fixtureRead(LIBOS_LOG_DECODE *which, LIBOS_LOG_DECODE_LOG *log) {
    (void)which;
    ++reads;
    if (blockRead && reads == 1) block_endpoint();
    log->record.meta = &metadata; log->record.log = log;
    log->record.timeStamp = reads >= completeAfter ? 0 : 1;
}
static void fixturePrint(LIBOS_LOG_DECODE *which, NvU64 *buffer, NvU64 count) {
    (void)which; (void)buffer; (void)count; ++prints;
}
static void fixtureNvlog(LIBOS_LOG_DECODE *which, NvBool sync) { (void)which; (void)sync; ++nvlogs; }
static void fixtureLog(int level, const char *format, ...) { (void)level; (void)format; }
static void *fixtureCopy(void *out, NvLength capacity, const void *in, NvLength bytes) {
    NvU8 *d = out; const NvU8 *s = in;
    if (bytes > capacity) __builtin_trap();
    ++copies;
    if (blockCopy && copies == 1) block_endpoint();
    for (NvLength i = 0; i < bytes; ++i) d[i] = s[i];
    return out;
}
static NvS32 fixtureCmp(const void *one, const void *two, NvLength bytes) {
    const NvU8 *a = one, *b = two;
    for (NvLength i = 0; i < bytes; ++i) if (a[i] != b[i]) return a[i] - b[i];
    return 0;
}

#undef osSpinLoop
#define osSpinLoop fixtureSpin
#define _kgspDumpGspLogsUnlocked fixtureDump
#undef osIsRaisedIRQL
#define osIsRaisedIRQL() NV_FALSE
#define libosExtractLog_ReadRecord fixtureRead
#define libosPrintLogRecords fixturePrint
#define libosExtractLogs_nvlog fixtureNvlog
#undef portMemCopy
#define portMemCopy fixtureCopy
#undef portMemCmp
#define portMemCmp fixtureCmp
#define LIBOS_LOG_TIMESTAMP_END 0
#define LIBOS_LOG_DECODE_PRINTF(...) fixtureLog(__VA_ARGS__)
#undef DBG_BREAKPOINT
#define DBG_BREAKPOINT() ((void)0)

#if S540_LOG_BASELINE
#include "baseline-bodies.inc"
#else
#include "proposed-bodies.inc"
#endif

void s540LogFixtureReset(NvU32 which, NvBool block) {
    NvU8 *d = (NvU8 *)&decoder;
    for (NvU64 i = 0; i < sizeof(decoder); ++i) d[i] = 0;
    d = (NvU8 *)&gsp; for (NvU64 i = 0; i < sizeof(gsp); ++i) d[i] = 0;
    entered = released = reads = copies = prints = logs = nvlogs = 0;
    blockRead = block && (which == 1 || which == 3);
    blockCopy = block && which == 2; blockSpin = block && which == 0;
    blockDump = block && which == 4;
    completeAfter = block ? 16 : 3;
    gsp.bInInit = NV_TRUE;
    gsp.logDumpLock = blockSpin ? 1 : 0;
    decoder.numLogBuffers = 1; decoder.bIsDecodable = NV_TRUE;
    decoder.scratchBuffer = scratch; decoder.scratchBufferSize = sizeof(scratch);
    decoder.mergedBuffer = merged; decoder.mergedBufferSize = sizeof(merged);
    decoder.log[0].physicLogBuffer = physical;
    decoder.log[0].logBufferSize = sizeof(physical);
    decoder.log[0].libosLogFlags = LIBOS_LOG_NVLOG_BUFFER_FLAG_MERGED_NVLOG_BUFFER;
    decoder.log[0].previousPut = 1;
    decoder.log[0].putCopy = decoder.log[0].putIter = 256;
    for (NvU64 i = 0; i < NV_ARRAY_ELEMENTS(physical); ++i) physical[i] = 0;
    physical[0] = 256;
    // Every two-word fixture record has timestamp1 and exact metadata size2.
    for (NvU64 i = 1; i < 257; i += 2) {
        physical[i] = REF_NUM64(LIBOS_LOG_METADATA_TOTAL_ARGS, 2);
        physical[i + 1] = 1;
    }
    mergedEntries = 0;
}
void s540LogFixtureRun(NvU32 which) {
    switch (which) {
    case 0: kgspDumpGspLogs_IMPL(&gsp, NV_FALSE); break;
    case 1: libosExtractLogs_decode(&decoder); break;
    case 2: libosMergeNvlog(&decoder, &mergedEntries); break;
    case 3: libosExtractLogs(&decoder, NV_FALSE); break;
    case 4: kgspDumpGspLogs_IMPL(&gsp, NV_FALSE); break;
    }
}
NvU32 s540LogFixtureEntered(void) { return __atomic_load_n(&entered, __ATOMIC_ACQUIRE); }
void s540LogFixtureRelease(void) { __atomic_store_n(&released, 1U, __ATOMIC_RELEASE); }
NvU32 s540LogFixtureReads(void) { return reads; }
NvU32 s540LogFixtureCopies(void) { return copies; }
NvU32 s540LogFixtureLogs(void) { return logs; }
NvU32 s540LogFixtureNvlogs(void) { return nvlogs; }
NvU32 s540LogFixturePrints(void) { return prints; }
NvU64 s540LogFixturePreviousPut(void) { return decoder.log[0].previousPut; }
NvU64 s540LogFixtureMergedEntries(void) { return mergedEntries; }
NvS32 s540LogFixtureLock(void) { return gsp.logDumpLock; }
