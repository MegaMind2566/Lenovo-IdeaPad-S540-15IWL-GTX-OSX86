// SPDX-License-Identifier: MIT
#include "S540NvidiaFirmwareAssets.hpp"
#include "../../nvidia-hardware-transport/firmware/S540NvidiaFirmware.hpp"

namespace S540NvidiaFirmwareAssets {
namespace {
constexpr NvU64 GspSize=22901632, UcodesSize=8837632;
constexpr NvU64 Fingerprint=0x8d1990ab6b98ae2bULL;
constexpr NvU32 Entries=496, Present=38;
const NvU8 GspHash[32]={0x0c,0x61,0x24,0xc1,0x1d,0x59,0x90,0x0a,0x05,0xab,0x54,0x61,0xe5,0xfc,0x70,0x87,0xfc,0x66,0x87,0xa1,0xba,0xde,0xad,0x49,0xa7,0xee,0xca,0x6e,0xd1,0x3e,0xeb,0x3b};
const NvU8 UcodesHash[32]={0x60,0x27,0xab,0x37,0x36,0xf7,0x33,0xb5,0xa0,0x6e,0x6e,0x61,0xaa,0xae,0x95,0x7d,0x1f,0x99,0x04,0x26,0xa2,0x63,0x84,0x9e,0xbc,0xfa,0x8a,0x49,0xee,0xb4,0xa5,0xd0};
const NvU8 BuildId[20]={0x4c,0x2b,0x93,0xff,0x78,0xc8,0x15,0x82,0x8b,0xdf,0x2b,0xb3,0x6c,0xbf,0x3b,0x17,0xc9,0xf0,0xe4,0x1b};
NvU32 get32(const NvU8 *b){return NvU32(b[0])|(NvU32(b[1])<<8)|(NvU32(b[2])<<16)|(NvU32(b[3])<<24);}
NvU64 get64(const NvU8 *b){return get32(b)|(NvU64(get32(b+4))<<32);}
void put32(NvU8 *b,NvU32 v){for(unsigned i=0;i<4;++i)b[i]=NvU8(v>>(8*i));}
void put64(NvU8 *b,NvU64 v){put32(b,NvU32(v));put32(b+4,NvU32(v>>32));}
bool equal(const NvU8 *a,const NvU8 *b,NvU64 n){NvU8 diff=0;for(NvU64 i=0;i<n;++i)diff|=a[i]^b[i];return diff==0;}
bool range(NvU64 offset,NvU64 size,NvU64 end){return offset<=end&&size<=end-offset;}
bool add(NvU64 a,NvU64 b,NvU64 *out){if(a>~NvU64(0)-b)return false;*out=a+b;return true;}
bool timesPage(NvU64 pages,NvU64 *bytes){if(pages>(~NvU64(0)>>12))return false;*bytes=pages<<12;return true;}
}

Error inspectUcodes(const void *bytes,NvU64 size,Ucodes *out){
    if(out==nullptr)return Error::Header;
    *out=Ucodes{};
    if(bytes==nullptr)return Error::Missing;
    // BINDATA_UCODES_BIN_HEADER is 24 bytes, followed by 24-byte native64
    // storage records. pData pointers must be null in this on-disk image.
    if(size<24||size>128ULL*1024*1024)return Error::Size;
    const NvU8 *b=static_cast<const NvU8 *>(bytes);
    if(get64(b)!=0x5345444f4355564eULL||get32(b+8)!=1)return Error::Header;
    NvU32 entries=get32(b+12);
    if(entries==0||entries>4096)return Error::Count;
    NvU64 directory=24+NvU64(entries)*24;
    if(!range(0,directory,size))return Error::Directory;
    NvU64 payloadStart=(directory+255)&~NvU64(255);
    NvU32 present=0;
    for(NvU32 i=0;i<entries;++i){
        const NvU8 *entry=b+24+NvU64(i)*24;
        NvU32 actual=get32(entry),compressed=get32(entry+4),flags=get32(entry+16),offset=get32(entry+20);
        NvU64 pointer=get64(entry+8);
        if(actual==0){if(compressed||pointer||flags||offset)return Error::Directory;continue;}
        ++present;
        // The approved pair uses uncompressed external records exclusively.
        // Other compression/flag profiles require a separately reviewed path.
        if(pointer!=0||flags!=4||compressed!=0)return Error::Directory;
        if((offset&255)!=0)return Error::Alignment;
        if(offset<payloadStart||!range(offset,actual,size))return Error::Range;
        for(NvU32 j=0;j<i;++j){
            const NvU8 *prior=b+24+NvU64(j)*24;NvU32 priorSize=get32(prior);
            if(priorSize!=0){NvU64 priorOffset=get32(prior+20);if(NvU64(offset)<priorOffset+priorSize&&priorOffset<NvU64(offset)+actual)return Error::Overlap;}
        }
    }
    if(present==0)return Error::Directory;
    *out=Ucodes{entries,present,get64(b+16),directory};return Error::Ok;
}

bool planRadix3(NvU64 dataBytes,NvU64 maxAllocationBytes,Radix3 *out){
    if(out==nullptr)return false;
    *out=Radix3{};
    if(dataBytes==0||dataBytes>~NvU64(0)-4095)return false;
    Radix3 p{};p.pages[3]=(dataBytes+4095)>>12;
    for(unsigned i=3;i>0;--i)p.pages[i-1]=((p.pages[i]-1)>>9)+1;
    if(p.pages[0]!=1)return false;
    NvU64 tablePages=0;
    for(unsigned i=0;i<3;++i)if(!add(tablePages,p.pages[i],&tablePages))return false;
    if(!timesPage(tablePages,&p.tableBytes)||!timesPage(p.pages[3],&p.dataBytes)||!add(p.tableBytes,p.dataBytes,&p.allocationBytes)||p.allocationBytes>maxAllocationBytes)return false;
    *out=p;return true;
}

Result verifyPair(const void *gsp,NvU64 gspSize,const void *ucodes,NvU64 ucodesSize){
    Result r{};r.cleanup=true;
    auto check=[&](bool ok){++r.checks;if(!ok)++r.failures;return ok;};
    if(!check(gsp!=nullptr&&ucodes!=nullptr))return r;
    if(!check(gspSize==GspSize&&ucodesSize==UcodesSize))return r;
    NvU8 digest[32]={};
    r.imageVerified=check(S540NvidiaFirmware::sha256(gsp,gspSize,digest)&&equal(digest,GspHash,32));
    r.ucodesVerified=check(S540NvidiaFirmware::sha256(ucodes,ucodesSize,digest)&&equal(digest,UcodesHash,32));
    for(unsigned i=0;i<32;++i)digest[i]=0;
    if(!r.imageVerified||!r.ucodesVerified)return r;
    S540NvidiaFirmware::Image image{};
    bool parsed=check(S540NvidiaFirmware::inspect(gsp,gspSize,&image)==S540NvidiaFirmware::Error::Ok);
    r.releaseMatched=parsed; // inspect enforces the exact NUL-terminated release.
    const NvU8 *gspBytes=static_cast<const NvU8 *>(gsp);
    r.signaturePresent=check(parsed&&image.signature.size==4096);
    check(parsed&&image.buildId.size==36&&equal(gspBytes+image.buildId.offset+16,BuildId,20));
    Ucodes directory{};r.ucodesDirectory=check(inspectUcodes(ucodes,ucodesSize,&directory)==Error::Ok);
    r.ucodesDirectory=check(r.ucodesDirectory&&directory.entries==Entries&&directory.present==Present&&directory.fingerprint==Fingerprint)&&r.ucodesDirectory;
    Radix3 first{},second{};
    r.radixLayout=check(parsed&&planRadix3(image.image.size,64ULL*1024*1024,&first)&&planRadix3(ucodesSize,64ULL*1024*1024,&second));
    check(first.pages[0]==1&&second.pages[0]==1&&first.tableBytes>0&&second.tableBytes>0);
    // No pointer/handle/allocated object escapes. Firmware is never executed.
    return r;
}

CheckResult selfCheck(){
    CheckResult r{};auto check=[&](bool ok){++r.checks;if(!ok)++r.failures;};
    NvU8 b[1024]={};Ucodes metadata{};
    auto fixture=[&](){for(unsigned i=0;i<sizeof(b);++i)b[i]=0;put64(b,0x5345444f4355564eULL);put32(b+8,1);put32(b+12,2);put64(b+16,Fingerprint);put32(b+24,32);put32(b+40,4);put32(b+44,256);put32(b+48,32);put32(b+64,4);put32(b+68,512);};
    fixture();check(inspectUcodes(b,sizeof(b),&metadata)==Error::Ok&&metadata.present==2&&metadata.directoryBytes==72);
    check(inspectUcodes(nullptr,1024,&metadata)==Error::Missing&&metadata.entries==0);
    check(inspectUcodes(b,23,&metadata)==Error::Size);
    check(inspectUcodes(b,128ULL*1024*1024+1,&metadata)==Error::Size);
    fixture();b[0]=0;check(inspectUcodes(b,sizeof(b),&metadata)==Error::Header);
    fixture();put32(b+8,2);check(inspectUcodes(b,sizeof(b),&metadata)==Error::Header);
    fixture();put32(b+12,0);check(inspectUcodes(b,sizeof(b),&metadata)==Error::Count);
    fixture();put32(b+12,4097);check(inspectUcodes(b,sizeof(b),&metadata)==Error::Count);
    fixture();put32(b+12,43);check(inspectUcodes(b,sizeof(b),&metadata)==Error::Directory);
    fixture();put32(b+48,0);check(inspectUcodes(b,sizeof(b),&metadata)==Error::Directory);
    fixture();put32(b+28,1);check(inspectUcodes(b,sizeof(b),&metadata)==Error::Directory);
    fixture();put64(b+32,1);check(inspectUcodes(b,sizeof(b),&metadata)==Error::Directory);
    fixture();put32(b+40,5);check(inspectUcodes(b,sizeof(b),&metadata)==Error::Directory);
    fixture();put32(b+44,257);check(inspectUcodes(b,sizeof(b),&metadata)==Error::Alignment);
    fixture();put32(b+44,0);check(inspectUcodes(b,sizeof(b),&metadata)==Error::Range);
    fixture();put32(b+44,1024);check(inspectUcodes(b,sizeof(b),&metadata)==Error::Range);
    fixture();put32(b+24,0xffffffffU);check(inspectUcodes(b,sizeof(b),&metadata)==Error::Range);
    fixture();put32(b+68,256);check(inspectUcodes(b,sizeof(b),&metadata)==Error::Overlap);
    fixture();put32(b+24,512);check(inspectUcodes(b,sizeof(b),&metadata)==Error::Overlap);
    fixture();put32(b+68,768);put32(b+48,256);check(inspectUcodes(b,sizeof(b),&metadata)==Error::Ok);
    Radix3 layout{};check(planRadix3(1,32768,&layout)&&layout.pages[0]==1&&layout.pages[1]==1&&layout.pages[2]==1&&layout.pages[3]==1&&layout.allocationBytes==16384);
    check(planRadix3(4096,16384,&layout)&&layout.dataBytes==4096);
    check(!planRadix3(0,32768,&layout)&&layout.allocationBytes==0);
    check(!planRadix3(1,16383,&layout));
    check(!planRadix3(~NvU64(0),~NvU64(0),&layout));
    check(!planRadix3(512ULL*512*512*4096+1,~NvU64(0),&layout));
    check(planRadix3(512ULL*512*512*4096,~NvU64(0),&layout)&&layout.pages[0]==1&&layout.pages[1]==512);
    check(!planRadix3(1,32768,nullptr));
    Result missing=verifyPair(nullptr,0,nullptr,0);check(!missing.passed()&&!missing.imageVerified&&!missing.ucodesVerified&&!missing.firmwareLoaded&&!missing.gpuInitialized);
    for(unsigned i=0;i<sizeof(b);++i)b[i]=0;
    return r;
}
}
