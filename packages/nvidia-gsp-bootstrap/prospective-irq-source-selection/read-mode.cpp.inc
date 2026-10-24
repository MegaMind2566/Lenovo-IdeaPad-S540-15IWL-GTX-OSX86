NV_STATUS readOriginalMode(Platform *p,S540GspIrqModeFacts &facts) {
    if(!p)return NV_ERR_INVALID_STATE;
    p->statistics.sourceProbeAttempted=1;
    p->statistics.sourceProbeReturned=0;
    p->statistics.sourceProbeStatus=NV_ERR_NOT_READY;
    p->statistics.sourceCount=p->statistics.sourcesObserved=p->statistics.messagedSources=0;
    p->statistics.inventoryValid=p->statistics.msiCapable=p->statistics.msixCapable=p->statistics.msiVectors=0;
    auto finish=[p](NV_STATUS status) {
        p->statistics.sourceProbeStatus=status;
        p->statistics.sourceProbeReturned=1;
        return status;
    };
    if(!ordinary(p)||!live(p))return finish(NV_ERR_INVALID_STATE);
    if(!p->provider->lockForArbitration(false))return finish(NV_ERR_BUSY_RETRY);
    S540NvidiaPci::Context pci;
    const bool bound=pci.bind(p->provider);
    S540NvidiaPci::Inventory inventory{};
    if(bound)inventory=pci.inventory();
    p->statistics.inventoryValid=inventory.valid;
    p->statistics.msiCapable=inventory.valid&&inventory.msiOffset!=0;
    p->statistics.msixCapable=inventory.valid&&inventory.msixOffset!=0;
    p->statistics.msiVectors=inventory.msiVectors;
    // The virtual property query performs Apple's lazy interrupt resolution.
    // Its complete published inventory, rather than PCI capability count,
    // bounds getInterruptType. A hardware MSI vector is not a source index.
    auto *controllers=OSDynamicCast(OSArray,p->provider->getProperty("IOInterruptControllers"));
    auto *specifiers=OSDynamicCast(OSArray,p->provider->getProperty("IOInterruptSpecifiers"));
    const NvU32 count=controllers?controllers->getCount():0;
    p->statistics.sourceCount=count;
    bool known=controllers&&specifiers&&count&&count<=32U&&specifiers->getCount()==count;
    NvU32 selected=0,messages=0,selectedType=0;
    if(known)for(NvU32 source=0;source<count;++source) {
        int type=0;
        if(p->provider->getInterruptType(static_cast<int>(source),&type)!=kIOReturnSuccess) {
            known=false;break;
        }
        ++p->statistics.sourcesObserved;
        if(type&kIOInterruptTypePCIMessaged) {
            ++messages;selected=source;selectedType=static_cast<NvU32>(type);
        }
    }
    p->statistics.messagedSources=messages;
    if(bound)pci.unbind();
    p->provider->unlockForArbitration();
    S540GspIrqModeFacts value{};
    value.known=known&&inventory.valid;
    value.interruptType=selectedType;
    value.messageSignaled=messages==1;
    value.msiCapable=p->statistics.msiCapable;
    value.msixCapable=p->statistics.msixCapable;
    value.msiVectors=inventory.msiVectors;
    if(!value.known||!value.messageSignaled||!value.msiCapable||value.msixCapable||value.msiVectors!=1)
        return finish(NV_ERR_NOT_SUPPORTED);
    // Every recheck must reproduce the selected source, source count and type.
    // A failed registration/arm never clears or substitutes this identity.
    if(p->irqSourceValid&&(p->irqSource!=selected||p->irqSourceCount!=count||
        p->statistics.selectedInterruptType!=selectedType))return finish(NV_ERR_INVALID_STATE);
    if(!p->irqSourceValid) {
        p->irqSource=selected;p->irqSourceCount=count;p->irqSourceValid=true;
        p->statistics.selectedSource=selected;
        p->statistics.selectedSourceValid=1;
        p->statistics.selectedInterruptType=selectedType;
        p->statistics.selectedTypeValid=1;
    }
    facts=value;return finish(NV_OK);
}
