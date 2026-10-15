/*
 * SPDX-FileCopyrightText: Copyright (c) 2014-2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: MIT
 *
 * Permission is hereby granted, free of charge, to any person obtaining a
 * copy of this software and associated documentation files (the "Software"),
 * to deal in the Software without restriction, including without limitation
 * the rights to use, copy, modify, merge, publish, distribute, sublicense,
 * and/or sell copies of the Software, and to permit persons to whom the
 * Software is furnished to do so, subject to the following conditions:
 *
 * The above copyright notice and this permission notice shall be included in
 * all copies or substantial portions of the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
 * THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
 * FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
 * DEALINGS IN THE SOFTWARE.
 */

/* Selected CPU-only NVPort runtime, externally serialized under the startup
 * lease. Requires the bounded reserve initialized and v6 memory fully cold.
 * Init/shutdown require an ordinary thread with interrupts enabled. This is
 * not complete NVPort, RM, security cryptography, IRQ support or a GPU API.
 */
#ifndef S540_NVPORT_RUNTIME_H
#define S540_NVPORT_RUNTIME_H
#include "../../nvidia-nvport-lifecycle/upstream/nvport_lifecycle.h"
#include "../../nvidia-os-adapter/upstream/nvport_time_uptime.h"
#include "nvport_runtime_utilities.h"
#include "nvport_runtime_safe.h"
#ifndef NV_MIN
#define NV_MIN(a,b) (((a) < (b)) ? (a) : (b))
#endif
#ifndef PORT_ASSERT_CHECKED
#define PORT_ASSERT_CHECKED(condition)
#endif
#ifndef PORT_IS_FUNC_SUPPORTED
#define PORT_IS_FUNC_SUPPORTED(function) function ## _SUPPORTED
#endif
#ifndef PORT_IS_MODULE_SUPPORTED
#define PORT_IS_MODULE_SUPPORTED(module) PORT_MODULE_ ## module
#endif
#define PORT_MODULE_time 1
#define portCryptoExTrueRandomGetU64_SUPPORTED 0
#ifdef __cplusplus
extern "C" {
#endif

/* Checked adaptation of core startup. Duplicate initialization is refused;
 * no reference count is hidden. Shutdown refuses consumer allocations or
 * custom allocators before releasing any PRNG or memory state. */
NV_STATUS s540NvportRuntimeInitialize(void);
NV_STATUS s540NvportRuntimeShutdown(void);
NvBool s540NvportRuntimeIsInitialized(void);
NvBool s540NvportRuntimeIsCold(void);

/* Original string APIs. Non-null valid buffers and non-overlap are required.
 * Copy: destSize/srcSize > 0. Cat: catSize > 0, destination terminated within
 * strSize. BufferToHex: bufSize <= NV_U64_MAX / 2. The defective grouped-hex
 * routine is absent. Length/substring/token APIs require terminated strings.
 */
NvS32 portStringCompare(const char *, const char *, NvLength);
NvS32 portStringCompareIgnoreCase(const char *, const char *, NvLength);
NvLength portStringCopy(char *, NvLength, const char *, NvLength);
char *portStringCat(char *, NvLength, const char *, NvLength);
NvLength portStringLength(const char *);
NvLength portStringLengthSafe(const char *, NvLength);
NvLength portStringConvertAsciiToUtf16(NvU16 *, NvLength, const char *, NvLength);
NvLength portStringBufferToHex(char *, NvLength, const NvU8 *, NvLength);
char *portStringTok(char *, const char *, char **);
char *portStringStrStr(char *, char *);
const char *portStringStrChar(const char *, int);

/* Exact upstream xorshift128+/splitmix64 PRNG, not security cryptography.
 * Objects require external serialization. No true RNG/hash APIs are exported.
 * Create failure returns NULL; Get/Fill require a non-null live generator.
 * Fill requires bufSize <= NV_U64_MAX - 7 and a valid writable buffer. The
 * default generator is mutable upstream state; reseeding can fail allocation,
 * leaving it NULL. Check it before subsequent use. */
typedef struct PORT_CRYPTO_PRNG PORT_CRYPTO_PRNG;
extern PORT_CRYPTO_PRNG *portCryptoDefaultGenerator;
void portCryptoInitialize(void);
void portCryptoShutdown(void);
PORT_CRYPTO_PRNG *portCryptoPseudoRandomGeneratorCreate(NvU64);
void portCryptoPseudoRandomGeneratorDestroy(PORT_CRYPTO_PRNG *);
NvU32 portCryptoPseudoRandomGeneratorGetU32(PORT_CRYPTO_PRNG *);
NvU64 portCryptoPseudoRandomGeneratorGetU64(PORT_CRYPTO_PRNG *);
NV_STATUS portCryptoPseudoRandomGeneratorFillBuffer(PORT_CRYPTO_PRNG *, NvU8 *, NvLength);
void portCryptoPseudoRandomSetSeed(NvU64);
NvU32 portCryptoPseudoRandomGetU32(void);
NvU64 portCryptoPseudoRandomGetU64(void);
NV_STATUS portCryptoPseudoRandomFillBuffer(NvU8 *, NvLength);
#ifdef __cplusplus
}
#endif
#endif
