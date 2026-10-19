/* SPDX-License-Identifier: MIT */
#ifndef S540_NVIDIA_FIRST_TXN_CONTEXT_H
#define S540_NVIDIA_FIRST_TXN_CONTEXT_H
#include "S540NvidiaGspContext.h"
#include "S540NvidiaGspFirstTransaction.h"
#ifdef __cplusplus
extern "C" {
#endif
/* Only the isolated context copy exports this. The production Owner has no
 * caller flag capable of admitting it and continues to refuse initialize. */
NV_STATUS s540GspContextBindFirstTransaction(S540GspContext *, S540GspCancellationToken);
#ifdef __cplusplus
}
#endif
#endif
