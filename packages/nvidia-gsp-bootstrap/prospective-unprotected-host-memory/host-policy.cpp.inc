struct UnprotectedCpuRegisters { NvU32 eax, ebx, ecx, edx; };
struct UnprotectedCpuObservation {
    NvU32 observedMask;
    UnprotectedCpuRegisters basic, signature, structured;
    NvU32 family, model;
};
// This is a private native observation primitive, not a caller-provided
// readiness flag. CPU-only controls replace this body in a generated fixture.
static void unprotectedCpuid(NvU32 leaf, NvU32 subleaf, UnprotectedCpuRegisters &out) {
#if defined(__x86_64__)
    __asm__ volatile("cpuid" : "=a"(out.eax), "=b"(out.ebx),
                     "=c"(out.ecx), "=d"(out.edx) : "0"(leaf), "2"(subleaf) : "memory");
#else
    (void)leaf; (void)subleaf; out = {};
#endif
}
static UnprotectedCpuObservation observeUnprotectedCpu() {
    UnprotectedCpuObservation value{};
    unprotectedCpuid(0, 0, value.basic); value.observedMask |= 1U;
    if (value.basic.eax >= 1U) {
        unprotectedCpuid(1, 0, value.signature); value.observedMask |= 2U;
        const NvU32 baseFamily = (value.signature.eax >> 8) & 15U;
        value.family = baseFamily == 15U ?
            baseFamily + ((value.signature.eax >> 20) & 255U) : baseFamily;
        value.model = (value.signature.eax >> 4) & 15U;
        if (baseFamily == 6U || baseFamily == 15U)
            value.model |= (value.signature.eax >> 12) & 240U;
    }
    if (value.basic.eax >= 7U) {
        unprotectedCpuid(7, 0, value.structured); value.observedMask |= 4U;
    }
    return value;
}
static bool supportsUnprotectedOwnedPages(const UnprotectedCpuObservation &cpu) {
    // Linux cpufeatures.h word4 = CPUID.1:ECX, word16 = CPUID.7.0:ECX.
    // TME is word16 bit13. The selected physical target is GenuineIntel
    // family6/model8e. A hidden/masked VMM is not cryptographically excluded.
    // SGX capability is separate: ordinary IOBuffer kernel pages are not EPC.
    return cpu.observedMask == 7U && cpu.basic.eax >= 7U &&
        cpu.basic.ebx == 0x756e6547U && cpu.basic.edx == 0x49656e69U &&
        cpu.basic.ecx == 0x6c65746eU && cpu.family == 6U && cpu.model == 0x8eU &&
        !(cpu.signature.ecx & (1U << 31)) && !(cpu.structured.ecx & (1U << 13));
}
static NvU32 unprotectedRequestLogged, allocationFailureLogs;
static_assert(__atomic_always_lock_free(sizeof(NvU32), nullptr),
              "Allocation diagnostics must not add a runtime lock");
static bool admitAllocationLog(NvBool unencrypted, NV_STATUS status) {
    const bool first = unencrypted == NV_TRUE &&
        __atomic_exchange_n(&unprotectedRequestLogged, 1U, __ATOMIC_RELAXED) == 0;
    if (first) return true;
    if (status == NV_OK) return false;
    NvU32 count = __atomic_load_n(&allocationFailureLogs, __ATOMIC_RELAXED);
    while (count < 16U) {
        if (__atomic_compare_exchange_n(&allocationFailureLogs, &count, count + 1U,
                false, __ATOMIC_RELAXED, __ATOMIC_RELAXED)) return true;
    }
    return false;
}
static void logAllocationRequest(NvU32 pages, NvU64 pageSize, NvBool contiguous,
    NvU32 cache, NvBool zeroed, NvBool unencrypted, NvS32 node,
    const UnprotectedCpuObservation &cpu, const char *stage, NV_STATUS status) {
    if (!ordinary() || !admitAllocationLog(unencrypted, status)) return;
    // Diagnostic only: no object pointers, allocation, IRQ logging or policy
    // mutation. Failure logging is bounded; ordinary successful calls are quiet.
#if defined(KERNEL)
    IOLog(
#else
    std::fprintf(stderr,
#endif
        "S540 NVIDIA memory: stage=%s status=0x%08x pages=%u page_bytes=%llu "
        "contiguous=%u cache=%u zeroed=%u unprotected=%u node=%d "
        "cpu_observed=0x%x max_basic=0x%x vendor=%08x:%08x:%08x "
        "signature=0x%08x family=0x%x model=0x%x leaf1_ecx=0x%08x leaf7_ecx=0x%08x\n",
        stage, static_cast<unsigned>(status), static_cast<unsigned>(pages),
        static_cast<unsigned long long>(pageSize), static_cast<unsigned>(contiguous),
        static_cast<unsigned>(cache), static_cast<unsigned>(zeroed),
        static_cast<unsigned>(unencrypted), static_cast<int>(node),
        static_cast<unsigned>(cpu.observedMask), static_cast<unsigned>(cpu.basic.eax),
        static_cast<unsigned>(cpu.basic.ebx), static_cast<unsigned>(cpu.basic.edx),
        static_cast<unsigned>(cpu.basic.ecx), static_cast<unsigned>(cpu.signature.eax),
        static_cast<unsigned>(cpu.family), static_cast<unsigned>(cpu.model),
        static_cast<unsigned>(cpu.signature.ecx), static_cast<unsigned>(cpu.structured.ecx));
}
