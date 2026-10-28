/* SPDX-License-Identifier: MIT */
#ifndef S540_PCI_TOPOLOGY_FACTS_H
#define S540_PCI_TOPOLOGY_FACTS_H
#include "../../nvidia-os-adapter/upstream/include/nvtypes.h"
#include "../../nvidia-os-adapter/upstream/include/nvstatus.h"
/* Private in-kernel references, never serialized or returned through an RPC.
 * Every handle belongs to the exact retained session and generation. The
 * backend verifies these tuples against real read-only configuration data.
 */
typedef struct S540PciTopologyReference {
    void *handle;
    NvU32 segment;
    NvU8 bus, device, function, reserved;
    NvU16 vendor, deviceId;
} S540PciTopologyReference;
typedef struct S540PciTopologyGspFacts {
    NvU32 format, bytes;
    S540PciTopologyReference fhb, chipset, upstream;
} S540PciTopologyGspFacts;
enum S540PciTopologyOperation {
    S540_PCI_TOPOLOGY_READ_BYTE = 1U,
    S540_PCI_TOPOLOGY_READ_WORD = 2U,
    S540_PCI_TOPOLOGY_READ_DWORD = 3U,
    S540_PCI_TOPOLOGY_WRITE_BYTE = 4U,
    S540_PCI_TOPOLOGY_WRITE_WORD = 5U,
    S540_PCI_TOPOLOGY_WRITE_DWORD = 6U
};
#ifdef __cplusplus
static_assert(sizeof(S540PciTopologyReference) == 24, "Private PCI reference layout changed");
static_assert(sizeof(S540PciTopologyGspFacts) == 80, "Private PCI GSP reference layout changed");
extern "C" {
#else
_Static_assert(sizeof(S540PciTopologyReference) == 24, "Private PCI reference layout changed");
_Static_assert(sizeof(S540PciTopologyGspFacts) == 80, "Private PCI GSP reference layout changed");
#endif
NV_STATUS s540PciTopologyValidateForGsp(const void *exactNv,
    const S540PciTopologyGspFacts *facts);
void s540PciTopologyRecordFailure(NvU32 operation, NV_STATUS status);
/* True only for this admitted bound backend's verified OS-config path. It
 * does not assert a physical host limitation or a global macOS capability.
 */
NvBool s540PciTopologyUsesOsConfig(const void *exactNv);
#ifdef __cplusplus
}
#endif
#endif
