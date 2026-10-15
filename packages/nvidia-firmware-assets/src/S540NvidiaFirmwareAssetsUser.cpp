// SPDX-License-Identifier: MIT
#ifdef KERNEL
#error The firmware file bridge is userspace-only.
#endif
#include "S540NvidiaFirmwareAssets.h"
#include "S540NvidiaFirmwareAssets.hpp"
#include "../../nvidia-hardware-transport/firmware/S540NvidiaFirmware.hpp"
#include <sys/stat.h>
#include <fcntl.h>
#include <unistd.h>
#include <cerrno>
#include <cstdlib>

namespace {
struct File { int fd; NvU8 *bytes; size_t size; };
bool same(const struct stat &a,const struct stat &b){return a.st_dev==b.st_dev&&a.st_ino==b.st_ino&&a.st_size==b.st_size&&a.st_mtime==b.st_mtime;}
bool closeFile(File &f){bool ok=true;if(f.fd>=0){ok=close(f.fd)==0;f.fd=-1;}if(f.bytes){std::free(f.bytes);f.bytes=nullptr;}f.size=0;return ok;}
bool readFile(int directory,const char *name,size_t expected,File *out,S540NvidiaFirmwareAssetReason *reason){
    // O_NONBLOCK prevents a hostile FIFO/device filename from blocking before
    // fstat can reject it. It has no effect on approved regular asset files.
    out->fd=openat(directory,name,O_RDONLY|O_NOFOLLOW|O_CLOEXEC|O_NONBLOCK);
    if(out->fd<0){*reason=errno==ENOENT?S540_NVIDIA_ASSETS_MISSING:S540_NVIDIA_ASSETS_UNSAFE_FILE;return false;}
    struct stat before{};
    if(fstat(out->fd,&before)!=0||!S_ISREG(before.st_mode)){*reason=S540_NVIDIA_ASSETS_UNSAFE_FILE;return false;}
    if(before.st_size<0||static_cast<uint64_t>(before.st_size)!=expected){*reason=S540_NVIDIA_ASSETS_SIZE_MISMATCH;return false;}
    out->bytes=static_cast<NvU8 *>(std::malloc(expected));
    if(!out->bytes){*reason=S540_NVIDIA_ASSETS_ALLOCATION_FAILED;return false;}
    out->size=expected;size_t used=0;
    while(used<expected){ssize_t n=read(out->fd,out->bytes+used,expected-used);if(n<0&&errno==EINTR)continue;if(n<=0){*reason=S540_NVIDIA_ASSETS_READ_FAILED;return false;}used+=static_cast<size_t>(n);}
    NvU8 extra;ssize_t trailing;
    do{trailing=read(out->fd,&extra,1);}while(trailing<0&&errno==EINTR);
    struct stat after{};
    if(trailing!=0||fstat(out->fd,&after)!=0||!same(before,after)){*reason=S540_NVIDIA_ASSETS_READ_FAILED;return false;}
    return true;
}
bool noticeMatches(const File &notice){
    const NvU8 expected[32]={0xc6,0x92,0xfb,0x14,0xad,0x4f,0x49,0x9c,0x6a,0xee,0x1b,0x9e,0x14,0x4e,0x69,0x05,0x14,0x8c,0x42,0x0e,0x62,0x25,0xb1,0x7c,0xb2,0x93,0x73,0x66,0xc1,0xe5,0x07,0xad};
    NvU8 digest[32];if(!S540NvidiaFirmware::sha256(notice.bytes,notice.size,digest))return false;
    NvU8 diff=0;for(unsigned i=0;i<32;++i){diff|=digest[i]^expected[i];digest[i]=0;}return diff==0;
}
}

extern "C" int s540_nvidia_firmware_assets_check(const char *directory,S540NvidiaFirmwareAssetResult *result){
    if(!result)return 0;
    *result=S540NvidiaFirmwareAssetResult{};result->format=1;result->cleanup=true;result->reason=S540_NVIDIA_ASSETS_INVALID_ARGUMENT;
    if(!directory)return 0;
    size_t n=0;while(n<4096&&directory[n])++n;if(n==0||n==4096)return 0;
    int dir=open(directory,O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC|O_NONBLOCK);
    if(dir<0){result->reason=errno==ENOENT?S540_NVIDIA_ASSETS_MISSING:S540_NVIDIA_ASSETS_UNSAFE_FILE;return 0;}
    File files[3]={{-1,nullptr,0},{-1,nullptr,0},{-1,nullptr,0}};
    const char *names[3]={"gsp_tu10x.bin","ucodes_tu10x.bin","NVIDIA-DRIVER-LICENSE.txt"};
    const size_t sizes[3]={22901632,8837632,22653};
    bool readAll=true;
    for(unsigned i=0;i<3;++i){++result->checks;if(!readFile(dir,names[i],sizes[i],&files[i],&result->reason)){readAll=false;break;}}
    if(readAll){
        result->present=true;result->gspSize=files[0].size;result->ucodesSize=files[1].size;
        S540NvidiaFirmwareAssets::Result pair=S540NvidiaFirmwareAssets::verifyPair(files[0].bytes,files[0].size,files[1].bytes,files[1].size);
        result->checks+=pair.checks+1;
        result->hashesVerified=pair.imageVerified&&pair.ucodesVerified&&noticeMatches(files[2]);
        result->containerParsed=pair.releaseMatched&&pair.signaturePresent;
        result->ucodesParsed=pair.ucodesDirectory;
        result->pairReady=pair.passed()&&result->hashesVerified;
        if(!result->hashesVerified)result->reason=S540_NVIDIA_ASSETS_HASH_MISMATCH;
        else if(!result->containerParsed)result->reason=S540_NVIDIA_ASSETS_CONTAINER_INVALID;
        else if(!result->ucodesParsed)result->reason=S540_NVIDIA_ASSETS_UCODES_INVALID;
        else if(!pair.radixLayout)result->reason=S540_NVIDIA_ASSETS_LAYOUT_INVALID;
        else if(!pair.passed())result->reason=S540_NVIDIA_ASSETS_CONTAINER_INVALID;
        else result->reason=S540_NVIDIA_ASSETS_VERIFIED;
        if(result->pairReady){
            S540NvidiaFirmware::Image image{};S540NvidiaFirmwareAssets::Ucodes metadata{};
            if(S540NvidiaFirmware::inspect(files[0].bytes,files[0].size,&image)!=S540NvidiaFirmware::Error::Ok||S540NvidiaFirmwareAssets::inspectUcodes(files[1].bytes,files[1].size,&metadata)!=S540NvidiaFirmwareAssets::Error::Ok){result->pairReady=false;result->reason=S540_NVIDIA_ASSETS_CONTAINER_INVALID;}
            else{result->imageSize=image.image.size;result->signatureSize=image.signature.size;result->sectionCount=uint32_t(files[0].bytes[60])|(uint32_t(files[0].bytes[61])<<8);result->ucodesEntryCount=metadata.entries;result->ucodesPresentCount=metadata.present;}
        }
    }
    bool cleanup=true;for(unsigned i=0;i<3;++i)if(!closeFile(files[i]))cleanup=false;
    if(close(dir)!=0)cleanup=false;
    result->cleanup=cleanup;
    if(!cleanup){result->pairReady=false;result->reason=S540_NVIDIA_ASSETS_CLEANUP_FAILED;}
    return result->pairReady?1:0;
}

extern "C" const char *s540_nvidia_firmware_assets_reason(uint32_t reason){
    switch(reason){
        case S540_NVIDIA_ASSETS_VERIFIED:return "verified_cpu_only";
        case S540_NVIDIA_ASSETS_INVALID_ARGUMENT:return "invalid_argument";
        case S540_NVIDIA_ASSETS_MISSING:return "missing_assets";
        case S540_NVIDIA_ASSETS_UNSAFE_FILE:return "unsafe_file";
        case S540_NVIDIA_ASSETS_SIZE_MISMATCH:return "size_mismatch";
        case S540_NVIDIA_ASSETS_READ_FAILED:return "read_failed";
        case S540_NVIDIA_ASSETS_ALLOCATION_FAILED:return "allocation_failed";
        case S540_NVIDIA_ASSETS_HASH_MISMATCH:return "hash_mismatch";
        case S540_NVIDIA_ASSETS_CONTAINER_INVALID:return "container_invalid";
        case S540_NVIDIA_ASSETS_UCODES_INVALID:return "ucodes_invalid";
        case S540_NVIDIA_ASSETS_LAYOUT_INVALID:return "layout_invalid";
        case S540_NVIDIA_ASSETS_CLEANUP_FAILED:return "cleanup_failed";
    }
    return "invalid_argument";
}
