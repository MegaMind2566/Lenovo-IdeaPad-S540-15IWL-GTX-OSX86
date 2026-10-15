/* SPDX-License-Identifier: MIT */
#include "../src/S540NvidiaFirmwareAssets.h"
#include <stdio.h>
#include <string.h>
int main(int argc,char **argv){
    S540NvidiaFirmwareAssetResult r;
    if(s540_nvidia_firmware_assets_check(NULL,&r)!=0||r.reason!=S540_NVIDIA_ASSETS_INVALID_ARGUMENT||!r.cleanup||r.pairReady)return 3;
    if(s540_nvidia_firmware_assets_check("/",NULL)!=0)return 3;
    if(strcmp(s540_nvidia_firmware_assets_reason(999U),"invalid_argument"))return 3;
    if(argc!=2)return 2;
    int ready=s540_nvidia_firmware_assets_check(argv[1],&r);
    printf("{\"format\":%u,\"component\":\"nvidia-firmware-assets-bridge\",\"execution\":\"native-user-space\",\"present\":%s,\"hashes_verified\":%s,\"container_parsed\":%s,\"ucodes_parsed\":%s,\"pair_ready\":%s,\"cleanup\":%s,\"gsp_size\":%llu,\"ucodes_size\":%llu,\"image_size\":%llu,\"signature_size\":%llu,\"section_count\":%u,\"ucodes_entry_count\":%u,\"ucodes_present_count\":%u,\"checks\":%u,\"reason\":\"%s\",\"firmware_loaded\":false,\"gpu_initialized\":false}\n",r.format,r.present?"true":"false",r.hashesVerified?"true":"false",r.containerParsed?"true":"false",r.ucodesParsed?"true":"false",r.pairReady?"true":"false",r.cleanup?"true":"false",(unsigned long long)r.gspSize,(unsigned long long)r.ucodesSize,(unsigned long long)r.imageSize,(unsigned long long)r.signatureSize,r.sectionCount,r.ucodesEntryCount,r.ucodesPresentCount,r.checks,s540_nvidia_firmware_assets_reason(r.reason));
    return ready?0:1;
}
