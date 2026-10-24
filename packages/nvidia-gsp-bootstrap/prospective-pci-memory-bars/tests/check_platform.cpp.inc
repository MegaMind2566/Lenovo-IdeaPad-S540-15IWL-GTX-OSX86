// Explicit CPU fixtures around the exact selected kernel function body.
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>
#include "@PLATFORM_HEADER@"
#include "@OBSERVATION_HEADER@"
#if !defined(__x86_64__) || !NVCPU_IS_X86_64
#error An actual x86_64 CPU compiler profile is required
#endif
#ifndef PROFILE_MODE
#error Explicit baseline/intermediate/current source selection required
#endif
using IOByteCount=NvU64;
constexpr unsigned kIOMemoryMapperNone=0;
enum Operation {Ordinary=1,Inactive,Segment,Lock,Bus,Slot,Function,Read32,Descriptor,Physical,Length,Read8,Read16,Unlock,Console};
static unsigned checks=0;
static std::vector<NvU64> trace;
static void observed(unsigned operation,unsigned argument=0){trace.push_back((NvU64(operation)<<32)|argument);}
static void require(bool value,const char *message){++checks;if(!value){std::fprintf(stderr,"failed: %s\n",message);std::abort();}}
class IODeviceMemory {
public:
    NvU64 physical=0,bytes=0,span=0;unsigned reg=0;
    NvU64 getPhysicalSegment(IOByteCount offset,IOByteCount *out,unsigned mapper){
        require(offset==0&&out&&mapper==kIOMemoryMapperNone,"exact descriptor metadata query");observed(Physical,reg);*out=span;return physical;
    }
    NvU64 getLength()const{observed(Length,reg);return bytes;}
};
class IOPCIDevice {
public:
    NvU8 config[256]{};IODeviceMemory memory[6]{};bool present[6]{};
    bool inactive=false,arbitration=true,locked=false;
    NvU8 bus=2,slot=0,function=0;
    unsigned lockAttempts=0,unlocks=0,read32s=0,read16s=0,read8s=0,writes=0;
    std::vector<unsigned> descriptorRegisters;
    void fixture32(unsigned offset,NvU32 value){require(offset<=252&&!(offset&3U),"fixture dword range");for(unsigned i=0;i<4;++i)config[offset+i]=NvU8(value>>(i*8));}
    void fixture16(unsigned offset,NvU16 value){require(offset<=254,"fixture word range");config[offset]=NvU8(value);config[offset+1]=NvU8(value>>8);}
    void memory32(unsigned offset,NvU64 address,NvU64 bytes){
        require(address<=0xffffffffULL&&!(address&15U),"fixture 32bit memory encoding");fixture32(offset,NvU32(address));
        unsigned index=(offset-0x10)/4;memory[index]={address,bytes,bytes,offset};present[index]=true;
    }
    void memory64(unsigned offset,NvU64 address,NvU64 bytes){
        require(offset<=0x20&&!(address&15U),"fixture 64bit memory encoding");fixture32(offset,NvU32(address)|4U);fixture32(offset+4,NvU32(address>>32));
        unsigned index=(offset-0x10)/4;memory[index]={address,bytes,bytes,offset};present[index]=true;
    }
    bool isInactive()const{observed(Inactive);return inactive;}
    bool lockForArbitration(bool wait){observed(Lock,wait);require(!wait&&!locked,"nonblocking arbitration");++lockAttempts;if(arbitration)locked=true;return arbitration;}
    void unlockForArbitration(){observed(Unlock);require(locked,"balanced actual arbitration unlock");locked=false;++unlocks;}
    NvU8 getBusNumber()const{observed(Bus);return bus;}
    NvU8 getDeviceNumber()const{observed(Slot);return slot;}
    NvU8 getFunctionNumber()const{observed(Function);return function;}
    NvU32 configRead32(NvU8 offset){
        require(locked&&offset<=252&&!(offset&3U),"config32 under arbitration");observed(Read32,offset);++read32s;
        return NvU32(config[offset])|NvU32(config[offset+1])<<8|NvU32(config[offset+2])<<16|NvU32(config[offset+3])<<24;
    }
    NvU16 configRead16(NvU8 offset){require(locked&&offset<=254,"config16 under arbitration");observed(Read16,offset);++read16s;return NvU16(config[offset])|NvU16(config[offset+1])<<8;}
    NvU8 configRead8(NvU8 offset){require(locked,"config8 under arbitration");observed(Read8,offset);++read8s;return config[offset];}
    void configWrite32(NvU8,NvU32){++writes;require(false,"collector cannot write PCI configuration");}
    IODeviceMemory *getDeviceMemoryWithRegister(NvU8 offset){
        require(locked&&offset>=0x10&&offset<=0x24&&!(offset&3U),"only six BAR registers may receive memory queries");
        observed(Descriptor,offset);descriptorRegisters.push_back(offset);unsigned index=(offset-0x10)/4;return present[index]?&memory[index]:nullptr;
    }
};
static IOPCIDevice *selectedProvider=nullptr;
static bool ordinaryContext=true,consoleExcluded=true,noImpl=false;
static unsigned segmentQueries=0,consoleQueries=0;
static NV_STATUS segmentStatus=NV_OK;
static bool ordinary(){observed(Ordinary);return ordinaryContext;}
static bool targetConsoleExcluded(IOPCIDevice *provider){require(provider==selectedProvider,"exact target for console fixture");observed(Console);++consoleQueries;return consoleExcluded;}
struct S540NvidiaGspPlatform::Context::Impl {IOPCIDevice *provider;};
S540NvidiaGspPlatform::Context::Context():impl_(noImpl?nullptr:new Impl{selectedProvider}){}
S540NvidiaGspPlatform::Context::~Context(){delete impl_;}
NV_STATUS S540NvidiaGspPlatform::Context::collectSegment(NvU32 &segment){observed(Segment);++segmentQueries;segment=0;return segmentStatus;}
@ACTUAL_BODY@
static NvU32 actualProductionPredicateMask(const S540GspDeviceFacts &deviceFacts){
    struct {S540PreparationObservation preparation{};} state;
@PREDICATE_ASSIGNMENT@
    return state.preparation.devicePredicates;
}
static void configure(IOPCIDevice &provider){
    provider.fixture32(0x00,0x1f9110deU);provider.fixture32(0x04,0x00100002U);
    provider.fixture32(0x08,0x030000a1U);provider.fixture32(0x2c,0x380617aaU);
    provider.fixture32(0x34,0x60U);
    provider.config[0x60]=1;provider.config[0x61]=0x68;provider.fixture16(0x64,0);
    provider.config[0x68]=5;provider.config[0x69]=0x78;
    provider.config[0x78]=0x10;provider.config[0x79]=0;provider.fixture16(0x7a,0x12);
@TARGET_CONFIG@
}
enum Mode {Target,NoIo,IoBefore,IoAddressBit2,MissingBar,MissingDescriptor,Mismatch,ShortSpan,ZeroLength,Overflow,FourthMemory,Final64,ReservedKind2,ReservedKind6,HighEvenDword,NoPcie,NoPm,NotD0,CapCycle,BadCapPointer,NoCapList,ConsoleOwner,SegmentFailure,WrongVendor,WrongDevice,WrongSubsystem,WrongClass,WrongRevision,MemoryDecodeOff,BadSlot,BadFunction,InactiveProvider,ArbitrationFailure,NotOrdinary,NoImpl,NullOutput};
static void mutate(IOPCIDevice &p,unsigned mode){
    switch(mode){
    case NoIo:p.fixture32(0x24,0);break;
    case IoBefore:{
        auto a=p.memory[0],b=p.memory[1],c=p.memory[3];
        for(unsigned offset=0x10;offset<=0x24;offset+=4)p.fixture32(offset,0);
        for(auto &present:p.present)present=false;
        p.fixture32(0x10,0x3001);p.memory32(0x14,a.physical,a.bytes);p.memory64(0x18,b.physical,b.bytes);p.memory64(0x20,c.physical,c.bytes);break;
    }
    case IoAddressBit2:p.fixture32(0x24,0x3005);break;
    case MissingBar:p.fixture32(0x1c,0);p.fixture32(0x20,0);break;
    case MissingDescriptor:p.present[1]=false;break;
    case Mismatch:p.memory[1].physical+=4096;break;
    case ShortSpan:p.memory[1].span=p.memory[1].bytes-1;break;
    case ZeroLength:p.memory[1].bytes=p.memory[1].span=0;break;
    case Overflow:p.memory64(0x1c,~NvU64(15),32);break;
    case FourthMemory:p.fixture32(0x24,0xa0000000);break;
    case Final64:p.fixture32(0x1c,0);p.fixture32(0x20,0);p.fixture32(0x24,4);break;
    case ReservedKind2:p.fixture32(0x10,0x93000002);break;
    case ReservedKind6:p.fixture32(0x10,0x93000006);break;
    case HighEvenDword:p.fixture32(0x18,0x80);p.memory[1].physical=0x8080000000ULL;break;
    case NoPcie:p.config[0x78]=9;break;
    case NoPm:p.config[0x60]=9;break;
    case NotD0:p.fixture16(0x64,1);break;
    case CapCycle:p.config[0x79]=0x60;break;
    case BadCapPointer:p.fixture32(0x34,0x3c);break;
    case NoCapList:p.fixture32(0x04,2);break;
    case ConsoleOwner:consoleExcluded=false;break;
    case SegmentFailure:segmentStatus=NV_ERR_NOT_READY;break;
    case WrongVendor:p.fixture32(0x00,0x1f918086);break;
    case WrongDevice:p.fixture32(0x00,0x1f9210de);break;
    case WrongSubsystem:p.fixture32(0x2c,0x380717aa);break;
    case WrongClass:p.fixture32(0x08,0x040300a1);break;
    case WrongRevision:p.fixture32(0x08,0x030000a2);break;
    case MemoryDecodeOff:p.fixture32(0x04,0x00100000);break;
    case BadSlot:p.slot=32;break;
    case BadFunction:p.function=8;break;
    case InactiveProvider:p.inactive=true;break;
    case ArbitrationFailure:p.arbitration=false;break;
    case NotOrdinary:ordinaryContext=false;break;
    case NoImpl:noImpl=true;break;
    default:break;
    }
}
static unsigned caseCount=0;
static std::vector<NvU64> targetTrace;
static void run(const char *name,unsigned mode,NV_STATUS wanted,NvU32 mask,int endpointType=-1){
    IOPCIDevice provider;configure(provider);ordinaryContext=true;consoleExcluded=true;segmentStatus=NV_OK;noImpl=false;
    mutate(provider,mode);if(endpointType>=0)provider.fixture16(0x7a,NvU16((unsigned(endpointType)<<4)|2U));
    selectedProvider=&provider;segmentQueries=consoleQueries=0;trace.clear();
    S540NvidiaGspPlatform::Context context;S540GspDeviceFacts facts{},before=facts;
    const NV_STATUS status=context.collectDeviceFacts(mode==NullOutput?nullptr:&facts,nullptr);
    const NvU32 predicates=actualProductionPredicateMask(facts);
    require(status==wanted,"actual selected body returns expected status");require(predicates==mask,"actual production observer returns expected predicates");
    require(provider.writes==0&&!provider.locked,"read-only endpoint and balanced arbitration");
    if(mode==InactiveProvider||mode==NotOrdinary||mode==NoImpl||mode==NullOutput||mode==ArbitrationFailure){
        require(!std::memcmp(&facts,&before,sizeof(facts)),"early refusal preserves output");
        require(provider.read32s==0&&provider.descriptorRegisters.empty()&&provider.unlocks==0,"early refusal performs no PCI reads or unlock");
    }else{
        require(provider.lockAttempts==1&&provider.unlocks==1&&provider.read32s==16&&segmentQueries==1&&consoleQueries==1,"bounded exact PCI collection lifecycle");
    }
    for(auto reg:provider.descriptorRegisters)require(reg!=0x30,"expansion ROM never counted as a memory BAR");
    if(mode==Target||mode==NoIo||mode==IoAddressBit2){
        require(provider.descriptorRegisters==std::vector<unsigned>({0x10,0x14,0x1c}),"three exact target memory registers; never the I/O BAR");
        require(facts.bars[0].physical==@MEMORY0@ULL&&facts.bars[1].physical==@MEMORY1@ULL&&facts.bars[2].physical==@MEMORY2@ULL,
            "actual above-4GiB registry-derived memory addresses preserved");
        if(mode==Target&&endpointType<0)targetTrace=trace;
        if(mode==NoIo||mode==IoAddressBit2)require(trace==targetTrace,"same endpoint call order with absent or optional I/O BAR");
    }
    if(mode==IoBefore)require(provider.descriptorRegisters==std::vector<unsigned>({0x14,0x18,0x20})&&facts.bars[0].offset==0x14&&facts.bars[1].offset==0x18&&facts.bars[2].offset==0x20,
        "I/O before memory is neither counted nor queried as MMIO");
    if(mode==HighEvenDword)require(facts.bars[1].physical==0x8080000000ULL&&provider.descriptorRegisters==std::vector<unsigned>({0x10,0x14,0x1c}),"64-bit high dword is consumed only by its own memory BAR");
    std::printf("%s{\"name\":\"%s\",\"status\":%u,\"predicates\":%u,\"bars_verified\":%u,\"no_coherent_gpu_memory\":%u,\"writes\":%u,\"trace\":[",
        caseCount++?",":"",name,status,predicates,unsigned(facts.barsVerified),unsigned(facts.noCoherentGpuMemoryProfile),provider.writes);
    for(unsigned i=0;i<trace.size();++i)std::printf("%s%llu",i?",":"",static_cast<unsigned long long>(trace[i]));
    std::puts("]}");
}
int main(){
    require(NV_ERR_NOT_READY==85,"pinned actual not-ready status");
    std::puts("{\"hardware_executed\":false,\"original_rm_executed\":false,\"cases\":[");
#if PROFILE_MODE==0
    run("authentic_resource_layout_B4",Target,NV_ERR_NOT_READY,59);
#elif PROFILE_MODE==1
    run("authentic_resource_layout_IO_only",Target,NV_ERR_NOT_READY,63);
#elif PROFILE_MODE==2
    run("authentic_resource_layout_combined",Target,NV_OK,127);
    run("same_memory_without_optional_IO",NoIo,NV_OK,127);
    run("IO_before_three_memory_BARs",IoBefore,NV_OK,127);
    run("IO_address_bit2_is_not_a_memory_kind",IoAddressBit2,NV_OK,127);
    run("missing_required_memory_BAR",MissingBar,NV_ERR_NOT_READY,123);
    run("missing_required_memory_descriptor",MissingDescriptor,NV_ERR_NOT_READY,59);
    run("mismatched_memory_descriptor_address",Mismatch,NV_ERR_NOT_READY,59);
    run("short_memory_descriptor_segment",ShortSpan,NV_ERR_NOT_READY,59);
    run("zero_memory_descriptor_length",ZeroLength,NV_ERR_NOT_READY,59);
    run("memory_address_plus_length_overflow",Overflow,NV_ERR_NOT_READY,59);
    run("unexpected_fourth_memory_BAR",FourthMemory,NV_ERR_NOT_READY,59);
    run("64bit_memory_encoding_in_final_BAR_slot",Final64,NV_ERR_NOT_READY,59);
    run("reserved_memory_kind2",ReservedKind2,NV_ERR_NOT_READY,59);
    run("reserved_memory_kind6",ReservedKind6,NV_ERR_NOT_READY,59);
    run("64bit_high_dword_not_reclassified",HighEvenDword,NV_OK,127);
    run("ordinary_PCIe_endpoint_type0",Target,NV_OK,127,0);
    run("legacy_PCIe_endpoint_type1",Target,NV_OK,127,1);
    for(int type=2;type<16;++type){char name[64];std::snprintf(name,sizeof(name),"non_endpoint_or_reserved_PCIe_type_%d",type);run(name,Target,NV_ERR_NOT_READY,63,type);}
    run("missing_PCIe_capability",NoPcie,NV_ERR_NOT_READY,63);
    run("missing_power_management_capability",NoPm,NV_ERR_NOT_READY,119);
    run("power_management_not_D0",NotD0,NV_ERR_NOT_READY,119);
    run("capability_list_cycle",CapCycle,NV_ERR_NOT_READY,63);
    run("capability_pointer_below_valid_range",BadCapPointer,NV_ERR_NOT_READY,55);
    run("capability_list_status_bit_absent",NoCapList,NV_ERR_NOT_READY,55);
    run("unexcluded_console_owner",ConsoleOwner,NV_ERR_NOT_READY,79);
    run("unknown_ACPI_segment",SegmentFailure,NV_ERR_NOT_READY,126);
    run("wrong_PCI_vendor",WrongVendor,NV_ERR_NOT_READY,57);
    run("wrong_PCI_device",WrongDevice,NV_ERR_NOT_READY,57);
    run("wrong_PCI_subsystem",WrongSubsystem,NV_ERR_NOT_READY,57);
    run("wrong_PCI_class",WrongClass,NV_ERR_NOT_READY,57);
    run("wrong_PCI_revision",WrongRevision,NV_ERR_NOT_READY,57);
    run("PCI_memory_decode_disabled",MemoryDecodeOff,NV_ERR_NOT_READY,57);
    run("invalid_PCI_slot",BadSlot,NV_ERR_NOT_READY,57);
    run("invalid_PCI_function",BadFunction,NV_ERR_NOT_READY,57);
    run("inactive_provider",InactiveProvider,NV_ERR_INVALID_STATE,0);
    run("arbitration_refused",ArbitrationFailure,NV_ERR_BUSY_RETRY,0);
    run("nonordinary_context",NotOrdinary,NV_ERR_INVALID_STATE,0);
    run("missing_context_Impl",NoImpl,NV_ERR_INVALID_STATE,0);
    run("null_output",NullOutput,NV_ERR_INVALID_STATE,0);
#else
#error Unknown source profile mode
#endif
    std::printf("],\"checks\":%u,\"case_count\":%u}\n",checks,caseCount);
}
