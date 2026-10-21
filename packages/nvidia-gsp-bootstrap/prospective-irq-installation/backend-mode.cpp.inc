// Read the actual current controller mode and a complete bounded standard PCI
// capability inventory. This first profile accepts only a single-vector MSI
// device without MSI-X; unknown or broader hardware requires another profile.
NV_STATUS readOriginalMode(Platform *p,S540GspIrqModeFacts &facts) {
    if(!ordinary(p)||!live(p))return NV_ERR_INVALID_STATE;
    if(!p->provider->lockForArbitration(false))return NV_ERR_BUSY_RETRY;
    S540NvidiaPci::Context pci;
    const bool bound=pci.bind(p->provider);
    S540NvidiaPci::Inventory inventory{};
    if(bound)inventory=pci.inventory();
    int type=0;
    const bool known=p->provider->getInterruptType(0,&type)==kIOReturnSuccess;
    if(bound)pci.unbind();
    p->provider->unlockForArbitration();
    S540GspIrqModeFacts value{};
    value.known=known&&inventory.valid;
    value.interruptType=static_cast<NvU32>(type);
    value.messageSignaled=known&&(type&kIOInterruptTypePCIMessaged);
    value.msiCapable=inventory.valid&&inventory.msiOffset!=0;
    value.msixCapable=inventory.valid&&inventory.msixOffset!=0;
    value.msiVectors=inventory.msiVectors;
    if(!value.known||!value.messageSignaled||!value.msiCapable||value.msixCapable||value.msiVectors!=1)
        return NV_ERR_NOT_SUPPORTED;
    facts=value;return NV_OK;
}
