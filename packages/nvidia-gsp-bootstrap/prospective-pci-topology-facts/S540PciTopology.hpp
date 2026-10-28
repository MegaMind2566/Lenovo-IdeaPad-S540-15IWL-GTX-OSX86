/* SPDX-License-Identifier: MIT */
#ifndef S540_PCI_TOPOLOGY_HPP
#define S540_PCI_TOPOLOGY_HPP
#include "S540PciTopologyFacts.h"

namespace S540NvidiaPciTopology {
constexpr NvU32 kMaximumBridges = 8U;
constexpr NvU32 kMaximumRecords = kMaximumBridges + 1U;
constexpr NvU32 kMaximumAncestry = 32U;
struct Candidate {
    void *resource;
    NvU32 segment;
    NvU8 bus, device, function;
    bool rootConfig;
};
struct Reader {
    void *context;
    NV_STATUS (*read)(void *, const Candidate &, NvU32, NvU32, NvU32 &);
};
struct Record {
    Candidate candidate;
    NvU32 identity, classRevision, headerType, buses;
    void *handle;
};
/* Ordinary, externally serialized Session-owned storage. None of these
 * records authorizes a configuration write, memory mapping or device DMA.
 */
struct State {
    const void *owner;
    NvU64 generation;
    NvU32 segment, count;
    NvU8 gpuBus;
    bool prepared;
    Reader reader;
    Record records[kMaximumRecords];
};
bool ready(const State &, const void *owner);
/* Candidates are the actual service ancestors, nearest bridge first, and
 * finally the actual FHB. The reader, not caller-supplied IDs, supplies facts.
 */
NV_STATUS prepare(State &, const void *owner, NvU32 segment, NvU8 gpuBus,
    const Reader &, const Candidate *, NvU32 count);
void *find(State &, const void *owner, NvU32 segment, NvU8 bus, NvU8 device,
    NvU8 function, NvU16 *vendor, NvU16 *deviceId);
NV_STATUS read(State &, const void *owner, void *handle, NvU32 offset,
    NvU32 width, NvU32 &value);
NV_STATUS validate(State &, const void *owner, const S540PciTopologyGspFacts &);
/* Only the existing successful backend stop may call this after releasing
 * its retained resources. The module generation issuer never resets.
 */
void clear(State &);
}

namespace S540NvidiaDeviceTransport {
struct Snapshot;
#if defined(KERNEL)
NV_STATUS prepareDarwinTopology(void *, const void *owner, const Snapshot &);
void *darwinTopologyHandle(void *, const void *owner, NvU32 segment, NvU8 bus,
    NvU8 device, NvU8 function, NvU16 *vendor, NvU16 *deviceId);
NV_STATUS readDarwinTopology(void *, const void *owner, void *handle,
    NvU32 offset, NvU32 width, NvU32 &value);
NV_STATUS validateDarwinTopology(void *, const void *owner,
    const Snapshot &, const S540PciTopologyGspFacts &);
bool darwinTopologyReady(void *, const void *owner);
#endif
}
#endif
