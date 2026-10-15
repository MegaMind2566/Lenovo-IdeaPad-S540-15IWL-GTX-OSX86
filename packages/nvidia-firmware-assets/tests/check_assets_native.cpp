// SPDX-License-Identifier: MIT
#include "../src/S540NvidiaFirmwareAssets.hpp"
#include <cstdio>
#include <fstream>
#include <vector>

static bool read(const char *path,std::vector<NvU8> *out){
    std::ifstream f(path,std::ios::binary|std::ios::ate);if(!f)return false;
    auto size=f.tellg();if(size<0||size>128*1024*1024)return false;
    out->resize(static_cast<size_t>(size));f.seekg(0);return bool(f.read(reinterpret_cast<char *>(out->data()),size));
}
int main(int argc,char **argv){
    using namespace S540NvidiaFirmwareAssets;
    CheckResult self=selfCheck();
    if(argc==1){std::printf("{\"format\":1,\"component\":\"nvidia-firmware-assets\",\"execution\":\"native-user-space\",\"checks\":%u,\"failures\":%u,\"real_image_verified\":false,\"firmware_loaded\":false,\"gpu_initialized\":false,\"status\":\"%s\"}\n",self.checks,self.failures,self.passed()?"passed":"failed");return self.passed()?0:1;}
    if(argc!=3)return 2;
    std::vector<NvU8> gsp,ucodes;if(!read(argv[1],&gsp)||!read(argv[2],&ucodes))return 2;
    Result r=verifyPair(gsp.data(),gsp.size(),ucodes.data(),ucodes.size());
    std::printf("{\"format\":1,\"component\":\"nvidia-firmware-assets\",\"execution\":\"native-user-space\",\"checks\":%u,\"failures\":%u,\"image_verified\":%s,\"ucodes_verified\":%s,\"release_matched\":%s,\"signature_present\":%s,\"ucodes_directory\":%s,\"radix_layout\":%s,\"cleanup\":%s,\"firmware_loaded\":false,\"gpu_initialized\":false,\"status\":\"%s\"}\n",r.checks+self.checks,r.failures+self.failures,r.imageVerified?"true":"false",r.ucodesVerified?"true":"false",r.releaseMatched?"true":"false",r.signaturePresent?"true":"false",r.ucodesDirectory?"true":"false",r.radixLayout?"true":"false",r.cleanup?"true":"false",r.passed()&&self.passed()?"passed":"failed");
    return r.passed()&&self.passed()?0:1;
}
