/* SPDX-License-Identifier: MIT */
#include "S540ExperimentalRuntime.h"
extern "C" {
extern const NvU8 s540_gsp_begin[], s540_gsp_end[];
extern const NvU8 s540_ucodes_begin[], s540_ucodes_end[];
extern const NvU8 s540ExperimentalNativeProfileBegin[], s540ExperimentalNativeProfileEnd[];
}
namespace {
bool targetBuild(const char *text) {
    const char expected[16]=S540_EXPERIMENTAL_TARGET_BUILD;
    NvU8 different=0;
    for(NvU32 i=0;i<16;++i) different|=NvU8(text[i]^expected[i]);
    return !different;
}
}
extern "C" NV_STATUS s540RuntimeReadCompiledProfile(S540ExperimentalNativeProfile *out) {
    if(!out) return NV_ERR_INVALID_ARGUMENT;
    const auto first=reinterpret_cast<NvUPtr>(s540ExperimentalNativeProfileBegin);
    const auto last=reinterpret_cast<NvUPtr>(s540ExperimentalNativeProfileEnd);
    if(last<first||last-first!=sizeof(S540ExperimentalNativeProfile))return NV_ERR_INVALID_DATA;
    S540ExperimentalNativeProfile value{};
    auto *to=reinterpret_cast<NvU8 *>(&value);
    for(NvU32 i=0;i<sizeof(value);++i)to[i]=s540ExperimentalNativeProfileBegin[i];
    NvU8 nonzero=0;
    for(NvU32 i=0;i<32;++i)nonzero|=value.codeContractSha256[i];
    if(value.format!=1||value.bytes!=sizeof(value)||!nonzero||!targetBuild(value.targetBuild)||
       value.workerStackBytes<8192||value.irqStackBytes<8192||value.workerStackBytes>16384||
       value.irqStackBytes>16384||value.frameworkAllowanceBytes!=2048||
       value.unknownAllowanceBytes!=4096||value.recursionAllowanceBytes!=1024||
       value.exceptionAllowanceBytes!=1024)return NV_ERR_INVALID_DATA;
    *out=value;return NV_OK;
}
extern "C" NV_STATUS s540RuntimeEmbeddedFirmware(const void **gsp,NvU64 *gspBytes,
    const void **ucodes,NvU64 *ucodesBytes) {
    if(!gsp||!gspBytes||!ucodes||!ucodesBytes)return NV_ERR_INVALID_ARGUMENT;
    const auto first=reinterpret_cast<NvUPtr>(s540_gsp_begin);
    const auto last=reinterpret_cast<NvUPtr>(s540_gsp_end);
    const auto second=reinterpret_cast<NvUPtr>(s540_ucodes_begin);
    const auto end=reinterpret_cast<NvUPtr>(s540_ucodes_end);
    if(last<first||end<second||last-first!=22901632||end-second!=8837632)return NV_ERR_INVALID_DATA;
    *gsp=s540_gsp_begin;*gspBytes=last-first;*ucodes=s540_ucodes_begin;*ucodesBytes=end-second;
    return NV_OK;
}
