/* Private pure optional-engine probes. They grant no physical permit. */
#ifndef S540_FIRST_TXN_OPTIONAL_NVLINK_PROBES_H
#define S540_FIRST_TXN_OPTIONAL_NVLINK_PROBES_H
#ifdef __cplusplus
extern "C" {
#endif
NV_STATUS s540FirstTxnOptionalNvlinkActive(const void *exactNv, NvU64 *generation);
NV_STATUS s540FirstTxnOptionalNvlinkReturned(const void *exactNv, NvU64 generation);
#ifdef __cplusplus
}
#endif
#endif
