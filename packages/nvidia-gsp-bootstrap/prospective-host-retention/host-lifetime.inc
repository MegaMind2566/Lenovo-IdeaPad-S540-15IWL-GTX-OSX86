// A lease is acquired before any dynamic guard access. A transition closes
// admission only from exactly zero leases; refusal never waits for callers.
constexpr NvU64 kHostClosed = 1ULL << 63;
constexpr NvU64 kHostTransition = 1ULL << 62;
constexpr NvU64 kHostUsers = kHostTransition - 1;
NvU64 hostLifetime = kHostClosed;
class HostUse {
    bool held_ = false;
public:
    HostUse() {
        NvU64 value = __atomic_load_n(&hostLifetime, __ATOMIC_ACQUIRE);
        for (;;) {
            if ((value & kHostClosed) || (value & kHostUsers) == kHostUsers) return;
            if (__atomic_compare_exchange_n(&hostLifetime, &value, value + 1,
                false, __ATOMIC_ACQ_REL, __ATOMIC_ACQUIRE)) { held_ = true; return; }
        }
    }
    ~HostUse() { if (held_) __atomic_fetch_sub(&hostLifetime, 1ULL, __ATOMIC_RELEASE); }
    explicit operator bool() const { return held_; }
    HostUse(const HostUse &) = delete;
    HostUse &operator=(const HostUse &) = delete;
};
