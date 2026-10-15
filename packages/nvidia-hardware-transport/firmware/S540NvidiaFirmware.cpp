// SPDX-License-Identifier: MIT
#include "S540NvidiaFirmware.hpp"

// Explicit hardened parser, not an unchanged upstream function. The exact ELF,
// section, release and RPC definitions are pinned in PROVENANCE.json.
namespace S540NvidiaFirmware {
namespace {
constexpr NvU64 MaxImage = 128ULL * 1024 * 1024;
constexpr NvU32 MaxSections = 512;
constexpr char Release[] = "615.78.08";
constexpr char Names[][24] = {".fwversion", ".fwimage", ".fwsignature_tu11x", ".note.gnu.build-id"};
constexpr NvU32 RpcVersion = 0x03000000U, RpcSignature = 0x43505256U;
constexpr NvU32 MctpMagic = 0x4d435450U, MctpSeen = 0x5345454eU;
constexpr NvU32 MctpHeader = 0xc0000001U, NvdmHeader = 0x2510de7eU;
constexpr NvU64 RpcPrefix = 24, RpcHeader = 32;
bool range(NvU64 offset, NvU64 length, NvU64 size) { return offset <= size && length <= size - offset; }
bool power2(NvU64 x) { return x != 0 && (x & (x - 1)) == 0; }
NvU16 le16(const NvU8 *b) { return NvU16(b[0]) | NvU16(NvU16(b[1]) << 8); }
NvU32 le32(const NvU8 *b) { return NvU32(b[0]) | (NvU32(b[1]) << 8) | (NvU32(b[2]) << 16) | (NvU32(b[3]) << 24); }
NvU64 le64(const NvU8 *b) { return le32(b) | (NvU64(le32(b + 4)) << 32); }
void put16(NvU8 *b, NvU16 v) { b[0] = NvU8(v); b[1] = NvU8(v >> 8); }
void put32(NvU8 *b, NvU32 v) { for (unsigned i = 0; i < 4; ++i) b[i] = NvU8(v >> (8 * i)); }
void put64(NvU8 *b, NvU64 v) { put32(b, NvU32(v)); put32(b + 4, NvU32(v >> 32)); }
void zero(void *p, NvU64 n) { NvU8 *b = static_cast<NvU8 *>(p); while (n--) *b++ = 0; }
bool eq(const NvU8 *b, const char *s, NvU64 n) { for (NvU64 i = 0; i < n; ++i) if (b[i] != NvU8(s[i])) return false; return true; }
NvU64 length(const char *s) { NvU64 n = 0; while (s[n]) ++n; return n; }
bool nameEq(const NvU8 *b, NvU64 n, const char *s) { NvU64 k = length(s); return n > k && eq(b,s,k) && b[k] == 0; }
bool overlap(Span a, Span b) { return a.size != 0 && b.size != 0 && a.offset < b.offset + b.size && b.offset < a.offset + a.size; }
bool alignUp(NvU64 x, NvU64 alignment, NvU64 *out) {
    if (!power2(alignment) || x > ~NvU64(0) - (alignment - 1)) return false;
    *out = (x + alignment - 1) & ~(alignment - 1); return true;
}
bool add(NvU64 a, NvU64 b, NvU64 *out) { if (a > ~NvU64(0) - b) return false; *out = a + b; return true; }
NvU32 rotate(NvU32 x, unsigned n) { return (x >> n) | (x << (32 - n)); }
const NvU32 K[64] = {
0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2};
void compress(NvU32 h[8], const NvU8 b[64]) {
    NvU32 w[64];
    for (unsigned i=0;i<16;++i) w[i]=(NvU32(b[4*i])<<24)|(NvU32(b[4*i+1])<<16)|(NvU32(b[4*i+2])<<8)|b[4*i+3];
    for (unsigned i=16;i<64;++i) { NvU32 a=w[i-15],z=w[i-2]; w[i]=w[i-16]+(rotate(a,7)^rotate(a,18)^(a>>3))+w[i-7]+(rotate(z,17)^rotate(z,19)^(z>>10)); }
    NvU32 a=h[0],c=h[2],b0=h[1],d=h[3],e=h[4],f=h[5],g=h[6],z=h[7];
    for(unsigned i=0;i<64;++i) {NvU32 t1=z+(rotate(e,6)^rotate(e,11)^rotate(e,25))+((e&f)^((~e)&g))+K[i]+w[i];NvU32 t2=(rotate(a,2)^rotate(a,13)^rotate(a,22))+((a&b0)^(a&c)^(b0&c));z=g;g=f;f=e;e=d+t1;d=c;c=b0;b0=a;a=t1+t2;}
    h[0]+=a;h[1]+=b0;h[2]+=c;h[3]+=d;h[4]+=e;h[5]+=f;h[6]+=g;h[7]+=z;
}
}

Error inspect(const void *bytes, NvU64 size, Image *out) {
    if (out == nullptr) return Error::Header;
    *out = Image{};
    if (bytes == nullptr || size == 0) return Error::MissingImage;
    if (size < 64 || size > MaxImage) return Error::Range;
    const NvU8 *b = static_cast<const NvU8 *>(bytes);
    if (le32(b) != 0x464c457f || b[4] != 2 || b[5] != 1 || b[6] != 1 || le32(b+20) != 1 || le16(b+52) != 64) return Error::Header;
    NvU64 table = le64(b+40), count = le16(b+60), namesIdx = le16(b+62);
    if (le16(b+58) != 64 || count < 2 || count > MaxSections || namesIdx == 0 || namesIdx >= count || !range(table,count*64,size) || table < 64) return Error::Range;
    if (table % 8 != 0) return Error::Alignment;
    NvU64 ph = le64(b+32), pn = le16(b+56);
    if (pn > MaxSections || (pn && (le16(b+54) != 56 || !range(ph,pn*56,size) || ph < 64 || ph % 8 != 0))) return Error::Range;
    const NvU8 *nh=b+table+namesIdx*64;
    NvU64 no=le64(nh+24), ns=le64(nh+32);
    if (le32(nh+4) != 3 || ns == 0 || ns > 65536 || no < 64 || !range(no,ns,size) || b[no] != 0 || b[no+ns-1] != 0) return Error::Names;
    Span selected[4] = {}; bool found[4] = {};
    Span tableSpan{table,count*64}, namesSpan{no,ns}, programsSpan{ph,pn*56};
    if (overlap(tableSpan,namesSpan) || overlap(tableSpan,programsSpan) || overlap(namesSpan,programsSpan)) return Error::Range;
    for (NvU64 i=0;i<count;++i) {
        const NvU8 *sh=b+table+i*64;
        NvU64 name=le32(sh), off=le64(sh+24), n=le64(sh+32), alignment=le64(sh+48);
        NvU32 type=le32(sh+4);
        if (name >= ns) return Error::Names;
        NvU64 end=name; while(end<ns && end-name<256 && b[no+end] != 0) ++end;
        if (end == ns || end-name == 256) return Error::Names;
        if (alignment > 1 && (!power2(alignment) || off % alignment != 0)) return Error::Alignment;
        if (type != 8 && !range(off,n,size)) return Error::Range;
        if (type != 8 && n && (off < 64 || overlap(Span{off,n},tableSpan) || overlap(Span{off,n},programsSpan))) return Error::Range;
        for(unsigned k=0;k<4;++k) if(nameEq(b+no+name,ns-name,Names[k])) {
            if(found[k]) return Error::Duplicate;
            if(n == 0 || type == 8 || type == 0 || off < 64 || overlap(Span{off,n},namesSpan)) return Error::Range;
            if ((k < 3 && type != 1) || (k == 3 && type != 7)) return Error::Header;
            found[k]=true;selected[k]=Span{off,n};
        }
    }
    for(unsigned k=0;k<4;++k) if(!found[k]) return Error::MissingSection;
    for(unsigned k=0;k<4;++k) for(unsigned j=k+1;j<4;++j) if(overlap(selected[k],selected[j])) return Error::Range;
    if(selected[0].size != sizeof(Release) || !eq(b+selected[0].offset,Release,sizeof(Release))) return Error::Version;
    // GNU build-id note: namesz=4, type=3, bounded nonempty descriptor.
    const NvU8 *note=b+selected[3].offset;NvU64 noteSize=selected[3].size;
    if(noteSize < 17 || le32(note) != 4 || le32(note+8) != 3 || !eq(note+12,"GNU\0",4)) return Error::BuildId;
    NvU64 desc=le32(note+4), rounded=0;
    if(desc == 0 || desc > 64 || !alignUp(desc,4,&rounded) || noteSize != 16+rounded) return Error::BuildId;
    // A firmware container is not executed as a host ELF. Validate any supplied
    // program-header ranges without assuming a host machine type.
    for(NvU64 i=0;i<pn;++i) {
        const NvU8 *p=b+ph+i*56;
        NvU64 off=le64(p+8),file=le64(p+32),mem=le64(p+40),a=le64(p+48),virtualEnd;
        if(!range(off,file,size)||file>mem||!add(le64(p+16),mem,&virtualEnd)) return Error::Range;
        if(a>1&&(!power2(a)||(off%a)!=(le64(p+16)%a))) return Error::Alignment;
    }
    *out = Image{selected[0],selected[1],selected[2],selected[3],size};
    return Error::Ok;
}

bool sha256(const void *bytes, NvU64 size, NvU8 digest[32]) {
    if (digest == nullptr) return false;
    zero(digest,32);
    if ((bytes == nullptr && size != 0) || size > MaxImage) return false;
    const NvU8 *b=static_cast<const NvU8 *>(bytes);NvU64 original=size;
    NvU32 h[8]={0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19};
    while(size>=64){compress(h,b);b+=64;size-=64;}
    NvU8 tail[128]={};for(NvU64 i=0;i<size;++i)tail[i]=b[i];tail[size]=0x80;
    unsigned n=size<56?64:128;NvU64 bits=original*8;
    for(unsigned i=0;i<8;++i)tail[n-1-i]=NvU8(bits>>(8*i));
    compress(h,tail);if(n==128)compress(h,tail+64);
    for(unsigned i=0;i<8;++i)for(unsigned j=0;j<4;++j)digest[4*i+j]=NvU8(h[i]>>(24-8*j));
    zero(tail,sizeof(tail));zero(h,sizeof(h));return true;
}

Error readiness(const void *bytes, NvU64 size, bool transportReady) {
    Image image{};Error e=inspect(bytes,size,&image);if(e!=Error::Ok)return e;
    NvU8 digest[32];if(!sha256(bytes,size,digest))return Error::Range;
    // Fail closed: no real firmware has been obtained and approved. A future
    // reviewed manifest must pin release, TU117 family, size and SHA256. Neither
    // an ELF version nor a synthetic fixture may authorize a firmware upload.
    zero(digest,sizeof(digest));
    (void)transportReady;
    return Error::UnapprovedImage;
}

bool planLayout(NvU64 commandBytes, NvU64 statusBytes, NvU64 maxBytes, Layout *out) {
    if(out==nullptr)return false;
    *out=Layout{};
    if(commandBytes==0||statusBytes==0||maxBytes==0)return false;
    // Page table, command header/data and status header/data, all page aligned.
    // This is allocation sizing only, not a GPU page table or DMA address map.
    Layout p{};p.commandHeader=4096;p.commandData=8192;NvU64 end;
    if(!add(p.commandData,commandBytes,&end)||!alignUp(end,4096,&p.statusHeader)||!add(p.statusHeader,4096,&p.statusData)||!add(p.statusData,statusBytes,&end)||!alignUp(end,4096,&p.total)||p.total>maxBytes)return false;
    // One 4 KiB page of 64-bit addresses can describe at most 512 pages.
    if(p.total/4096>512)return false;
    *out=p;return true;
}

Error validateRpc(const void *bytes, NvU64 size, NvU32 expectedSequence) {
    if(bytes==nullptr||size<RpcPrefix+RpcHeader||size>65536)return Error::RpcLength;
    const NvU8 *b=static_cast<const NvU8 *>(bytes);
    if(le32(b)==MctpSeen)return Error::Stale;
    if(le32(b)!=MctpMagic||le32(b+8)!=MctpHeader||le32(b+12)!=NvdmHeader||le32(b+20)!=0)return Error::RpcHeader;
    NvU32 full=le32(b+4),payload=le32(b+16);
    if(full!=size||payload!=size-RpcPrefix||payload<RpcHeader||(payload%4)!=0)return Error::RpcLength;
    b+=RpcPrefix;
    if(le32(b)!=RpcVersion||le32(b+4)!=RpcSignature)return Error::RpcHeader;
    if(le32(b+8)!=payload)return Error::RpcLength;
    if(le32(b+24)!=expectedSequence)return Error::RpcSequence;
    return Error::Ok;
}
Error begin(RpcWindow *w, NvU32 sequence, NvU64 now, NvU64 timeout) {
    if(w==nullptr)return Error::RpcHeader;
    if(w->pending)return Error::Busy;
    NvU64 deadline;if(timeout==0||!add(now,timeout,&deadline))return Error::Timeout;
    *w=RpcWindow{true,sequence,deadline};return Error::Ok;
}
Error complete(RpcWindow *w, const void *bytes, NvU64 size, NvU64 now) {
    if(w==nullptr||!w->pending)return Error::Stale;
    if(now>=w->deadline){cancel(w);return Error::Timeout;}
    Error e=validateRpc(bytes,size,w->sequence);if(e==Error::Ok)cancel(w);return e;
}
void cancel(RpcWindow *w) { if(w)*w=RpcWindow{}; }

namespace {
// Synthetic, non-executable fixtures. Never an approved firmware image.
void fixture(NvU8 b[1024]) {
    zero(b,1024);put32(b,0x464c457f);b[4]=2;b[5]=1;b[6]=1;put32(b+20,1);put16(b+52,64);put64(b+40,64);put16(b+58,64);put16(b+60,6);put16(b+62,1);
    const char strings[]="\0.shstrtab\0.fwversion\0.fwimage\0.fwsignature_tu11x\0.note.gnu.build-id\0";
    for(unsigned i=0;i<sizeof(strings);++i)b[448+i]=NvU8(strings[i]);
    const NvU32 name[5]={1,11,22,31,50};const NvU64 off[5]={448,544,560,576,592},n[5]={sizeof(strings),sizeof(Release),16,16,20};
    for(unsigned i=0;i<5;++i){NvU8 *s=b+64+(i+1)*64;put32(s,name[i]);put32(s+4,i==0?3:(i==4?7:1));put64(s+24,off[i]);put64(s+32,n[i]);put64(s+48,1);}
    for(unsigned i=0;i<sizeof(Release);++i)b[544+i]=NvU8(Release[i]);
    put32(b+592,4);put32(b+596,4);put32(b+600,3);b[604]='G';b[605]='N';b[606]='U';put32(b+608,0x12345678);
}
void rpcFixture(NvU8 b[56],NvU32 sequence) {zero(b,56);put32(b,MctpMagic);put32(b+4,56);put32(b+8,MctpHeader);put32(b+12,NvdmHeader);put32(b+16,32);put32(b+24,RpcVersion);put32(b+28,RpcSignature);put32(b+32,32);put32(b+48,sequence);}
}
Result selfCheck() {
    Result r{};r.parser=r.rpc=r.layout=r.cleanup=true;r.realImageReady=false;
    auto check=[&](bool condition,bool &group){++r.checks;if(!condition){++r.failures;group=false;}};
    NvU8 b[1024];fixture(b);Image image{};
    check(inspect(b,sizeof(b),&image)==Error::Ok,r.parser);
    check(image.image.offset==560&&image.signature.offset==576&&image.buildId.size==20,r.parser);
    check(inspect(nullptr,1024,&image)==Error::MissingImage&&image.size==0,r.parser);
    check(inspect(b,63,&image)==Error::Range,r.parser);
    check(inspect(b,MaxImage+1,&image)==Error::Range,r.parser);
    check(inspect(b,sizeof(b),nullptr)==Error::Header,r.parser);
    const NvU64 mutateOff[]={0,4,5,6,20,52,58,60,62};
    for(unsigned i=0;i<9;++i){fixture(b);NvU8 old=b[mutateOff[i]];b[mutateOff[i]]=0;check(inspect(b,sizeof(b),&image)!=Error::Ok,r.parser);b[mutateOff[i]]=old;}
    fixture(b);put64(b+40,~NvU64(0)-31);check(inspect(b,sizeof(b),&image)==Error::Range,r.parser);
    fixture(b);put64(b+40,65);check(inspect(b,sizeof(b),&image)==Error::Alignment,r.parser);
    fixture(b);put16(b+62,6);check(inspect(b,sizeof(b),&image)==Error::Range,r.parser);
    fixture(b);put64(b+32,672);put16(b+54,56);put16(b+56,1);
    put64(b+672+8,560);put64(b+672+16,560);put64(b+672+32,16);put64(b+672+40,16);put64(b+672+48,8);
    check(inspect(b,sizeof(b),&image)==Error::Ok,r.parser);
    put64(b+672+40,15);check(inspect(b,sizeof(b),&image)==Error::Range,r.parser);
    put64(b+672+40,16);put64(b+672+16,~NvU64(0)-7);check(inspect(b,sizeof(b),&image)==Error::Range,r.parser);
    put64(b+672+16,561);check(inspect(b,sizeof(b),&image)==Error::Alignment,r.parser);
    put64(b+672+16,560);put64(b+672+8,1024);check(inspect(b,sizeof(b),&image)==Error::Range,r.parser);
    fixture(b);put64(b+32,64);put16(b+54,56);put16(b+56,1);check(inspect(b,sizeof(b),&image)==Error::Range,r.parser);
    fixture(b);put64(b+32,672);put16(b+54,56);put16(b+56,513);check(inspect(b,sizeof(b),&image)==Error::Range,r.parser);
    fixture(b);put64(b+64+64+32,~NvU64(0));check(inspect(b,sizeof(b),&image)==Error::Names,r.parser);
    fixture(b);b[448]=1;check(inspect(b,sizeof(b),&image)==Error::Names,r.parser);
    fixture(b);put32(b+64+2*64,0xffffffff);check(inspect(b,sizeof(b),&image)==Error::Names,r.parser);
    fixture(b);put64(b+64+3*64+24,1024);check(inspect(b,sizeof(b),&image)==Error::Range,r.parser);
    fixture(b);put64(b+64+3*64+48,3);check(inspect(b,sizeof(b),&image)==Error::Alignment,r.parser);
    fixture(b);put64(b+64+3*64+48,32);check(inspect(b,sizeof(b),&image)==Error::Alignment,r.parser);
    fixture(b);put32(b+64+3*64+4,8);check(inspect(b,sizeof(b),&image)==Error::Range,r.parser);
    fixture(b);put64(b+64+3*64+24,64);check(inspect(b,sizeof(b),&image)==Error::Range,r.parser);
    fixture(b);put64(b+64+3*64+24,544);check(inspect(b,sizeof(b),&image)==Error::Range,r.parser);
    fixture(b);put32(b+64+3*64,11);check(inspect(b,sizeof(b),&image)==Error::Duplicate,r.parser);
    fixture(b);put32(b+64+3*64,0);check(inspect(b,sizeof(b),&image)==Error::MissingSection,r.parser);
    fixture(b);b[544]='9';check(inspect(b,sizeof(b),&image)==Error::Version,r.parser);
    fixture(b);b[553]='x';check(inspect(b,sizeof(b),&image)==Error::Version,r.parser);
    fixture(b);put32(b+596,0);check(inspect(b,sizeof(b),&image)==Error::BuildId,r.parser);
    fixture(b);put32(b+596,65);check(inspect(b,sizeof(b),&image)==Error::BuildId,r.parser);
    fixture(b);b[604]='X';check(inspect(b,sizeof(b),&image)==Error::BuildId,r.parser);
    fixture(b);check(readiness(b,sizeof(b),true)==Error::UnapprovedImage,r.parser);
    check(readiness(b,sizeof(b),false)==Error::UnapprovedImage,r.parser);
    check(readiness(nullptr,0,false)==Error::MissingImage,r.parser);
    NvU8 digest[32];const NvU8 abcExpected[32]={0xba,0x78,0x16,0xbf,0x8f,0x01,0xcf,0xea,0x41,0x41,0x40,0xde,0x5d,0xae,0x22,0x23,0xb0,0x03,0x61,0xa3,0x96,0x17,0x7a,0x9c,0xb4,0x10,0xff,0x61,0xf2,0x00,0x15,0xad};
    check(sha256("abc",3,digest),r.parser);bool digestOk=true;for(unsigned i=0;i<32;++i)digestOk&=digest[i]==abcExpected[i];check(digestOk,r.parser);
    check(sha256(nullptr,0,digest)&&digest[0]==0xe3&&digest[31]==0x55,r.parser);
    check(!sha256(nullptr,1,digest)&&digest[0]==0,r.parser);
    check(!sha256(b,MaxImage+1,digest),r.parser);
    Layout layout{};check(planLayout(4096,8192,32768,&layout),r.layout);
    check(layout.commandHeader==4096&&layout.commandData==8192&&layout.statusHeader==12288&&layout.statusData==16384&&layout.total==24576,r.layout);
    check(!planLayout(0,8192,32768,&layout)&&layout.total==0,r.layout);
    check(!planLayout(4096,0,32768,&layout),r.layout);
    check(!planLayout(~NvU64(0),8192,32768,&layout),r.layout);
    check(!planLayout(4096,~NvU64(0),~NvU64(0),&layout),r.layout);
    check(!planLayout(4096,8192,24575,&layout),r.layout);
    check(!planLayout(4*1024*1024,8192,8*1024*1024,&layout),r.layout);
    check(planLayout(1,1,32768,&layout)&&layout.total==20480,r.layout);
    NvU8 rpc[56];rpcFixture(rpc,17);check(validateRpc(rpc,56,17)==Error::Ok,r.rpc);
    check(validateRpc(nullptr,56,17)==Error::RpcLength,r.rpc);
    check(validateRpc(rpc,55,17)==Error::RpcLength,r.rpc);
    check(validateRpc(rpc,65537,17)==Error::RpcLength,r.rpc);
    check(validateRpc(rpc,56,18)==Error::RpcSequence,r.rpc);
    const unsigned rpcFields[]={0,4,8,12,16,20,24,28,32};
    for(unsigned i=0;i<9;++i){rpcFixture(rpc,17);rpc[rpcFields[i]]^=0xff;check(validateRpc(rpc,56,17)!=Error::Ok,r.rpc);}
    rpcFixture(rpc,17);put32(rpc,MctpSeen);check(validateRpc(rpc,56,17)==Error::Stale,r.rpc);
    RpcWindow window{};rpcFixture(rpc,17);
    check(begin(&window,17,100,50)==Error::Ok,r.rpc);
    check(begin(&window,18,101,50)==Error::Busy&&window.sequence==17,r.rpc);
    check(complete(&window,rpc,56,149)==Error::Ok&&!window.pending,r.rpc);
    check(complete(&window,rpc,56,149)==Error::Stale,r.rpc);
    check(begin(&window,17,100,50)==Error::Ok,r.rpc);
    check(complete(&window,rpc,56,150)==Error::Timeout&&!window.pending,r.rpc);
    check(begin(&window,17,~NvU64(0)-1,2)==Error::Timeout&&!window.pending,r.rpc);
    check(begin(&window,17,0,0)==Error::Timeout,r.rpc);
    check(begin(&window,0xffffffffU,0,1)==Error::Ok,r.rpc);rpcFixture(rpc,0xffffffffU);
    check(complete(&window,rpc,56,0)==Error::Ok,r.rpc);
    check(begin(&window,0,0,1)==Error::Ok,r.rpc);rpcFixture(rpc,0);
    check(complete(&window,rpc,56,0)==Error::Ok,r.rpc);
    check(begin(&window,1,0,2)==Error::Ok,r.rpc);rpcFixture(rpc,2);
    check(complete(&window,rpc,56,1)==Error::RpcSequence&&window.pending,r.rpc);
    cancel(&window);check(!window.pending&&window.sequence==0&&window.deadline==0,r.cleanup);
    check(image.size==0,r.cleanup); // all rejected parse outputs were cleared
    zero(b,sizeof(b));zero(rpc,sizeof(rpc));zero(digest,sizeof(digest));
    return r;
}
}
