// SPDX-License-Identifier: MIT
#pragma once
#include "S540NvidiaDarwinInternal.hpp"
// Transaction records are outside this callback backend test. Any attempt to
// bind/admit one trips a fixture failure rather than fabricating acceptance.
enum { S540_FIRST_SERVICE_ADMIT=1, S540_FIRST_SERVICE_ENTER=2, S540_FIRST_SERVICE_RETURNED=3 };
struct S540FirstTxnServiceContext {
    NvU32 stage; NvU64 thread; const void *data; NvU64 generation;
};
extern "C" inline NV_STATUS s540FirstTxnWorkRejected(const void *,os_work_queue *,void *,NV_STATUS) {
    throw std::runtime_error("transaction hook outside callback fixture");
}
extern "C" inline NV_STATUS s540FirstTxnWorkEnter(const void *,os_work_queue *,void *,NvU64) {
    throw std::runtime_error("transaction hook outside callback fixture");
}
extern "C" inline NV_STATUS s540FirstTxnWorkReturned(const void *,os_work_queue *,NvU64) {
    throw std::runtime_error("transaction hook outside callback fixture");
}
extern "C" inline NV_STATUS s540FirstTxnWorkRetain(const void *,os_work_queue *,NvU64,NV_STATUS) {
    throw std::runtime_error("transaction hook outside callback fixture");
}
extern "C" inline NV_STATUS s540FirstTxnWorkAdmit(const void *,os_work_queue *,void *,NvU64 *) {
    throw std::runtime_error("transaction hook outside callback fixture");
}
