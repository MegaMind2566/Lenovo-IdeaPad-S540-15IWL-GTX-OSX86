#include "../firmware/S540NvidiaFirmware.hpp"
#include <cstdio>
#include <cstring>

int main() {
    using namespace S540NvidiaFirmware;
    Result r=selfCheck();
    // Independent standard vectors cover padding on both sides of 56 bytes.
    const char *messages[]={"", "abc", "abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq"};
    const char *expected[]={"e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855", "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad", "248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1"};
    const char hex[]="0123456789abcdef";
    for(unsigned i=0;i<3;++i){NvU8 digest[32];char text[65];bool ok=sha256(messages[i],std::strlen(messages[i]),digest);for(unsigned j=0;j<32;++j){text[2*j]=hex[digest[j]>>4];text[2*j+1]=hex[digest[j]&15];}text[64]=0;++r.checks;if(!ok||std::strcmp(text,expected[i])){++r.failures;r.parser=false;}}
    // Every short, deliberately malformed CPU buffer must fail closed. The
    // bytes are fixtures, not a firmware binary or a GPU response.
    NvU8 malformed[256];for(unsigned i=0;i<sizeof(malformed);++i)malformed[i]=NvU8(i*13+7);
    for(unsigned n=0;n<=sizeof(malformed);++n){Image output{};Error e=inspect(malformed,n,&output);++r.checks;if(e==Error::Ok||output.size!=0){++r.failures;r.parser=false;}}
    std::printf("{\"format\":1,\"component\":\"nvidia-firmware-transport\",\"execution\":\"native-user-space\",\"kernel_runtime\":\"not_tested\",\"gpu_access\":false,\"checks\":%u,\"failures\":%u,\"parser\":%s,\"rpc\":%s,\"layout\":%s,\"cleanup\":%s,\"real_image_ready\":false,\"status\":\"%s\"}\n",r.checks,r.failures,r.parser?"true":"false",r.rpc?"true":"false",r.layout?"true":"false",r.cleanup?"true":"false",r.passed()?"passed":"failed");
    return r.passed()&&!r.realImageReady?0:1;
}
