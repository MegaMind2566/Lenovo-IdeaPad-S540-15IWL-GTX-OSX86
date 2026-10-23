#include <cstdio>
#include <cstdlib>
#include <cstring>
#include "../S540ExperimentalRuntime.h"
int main(int argc,char **argv) {
    if(argc!=3)return 2;
    const bool goodProfile=argv[1][0]=='1',goodFirmware=argv[2][0]=='1';
    S540ExperimentalNativeProfile profile;
    std::memset(&profile,0x5a,sizeof(profile));
    const auto old=profile;
    const NV_STATUS status=s540RuntimeReadCompiledProfile(&profile);
    if((status==NV_OK)!=goodProfile)std::abort();
    if(!goodProfile&&std::memcmp(&profile,&old,sizeof(profile)))std::abort();
    const void *gsp=reinterpret_cast<const void *>(1),*ucodes=reinterpret_cast<const void *>(2);
    NvU64 gspBytes=3,ucodesBytes=4;
    const NV_STATUS firmware=s540RuntimeEmbeddedFirmware(&gsp,&gspBytes,&ucodes,&ucodesBytes);
    if((firmware==NV_OK)!=goodFirmware)std::abort();
    if(goodFirmware&&(gspBytes!=22901632||ucodesBytes!=8837632))std::abort();
    if(!goodFirmware&&(gsp!=reinterpret_cast<const void *>(1)||ucodes!=reinterpret_cast<const void *>(2)||gspBytes!=3||ucodesBytes!=4))std::abort();
    if(s540RuntimeReadCompiledProfile(nullptr)!=NV_ERR_INVALID_ARGUMENT||
       s540RuntimeEmbeddedFirmware(nullptr,&gspBytes,&ucodes,&ucodesBytes)!=NV_ERR_INVALID_ARGUMENT)std::abort();
    std::puts("{\"profile_boundary_controls\":4,\"real_firmware_embedded\":false}");
}
