namespace {
Guard *retainedBackendHead;
NvU64 backendReleaseRefusals;
}
void retainBackend(Guard *guard,NvU32 bytes) {
    __atomic_add_fetch(&backendReleaseRefusals,1ULL,__ATOMIC_RELAXED);
    NvU32 empty=0;
    if(!__atomic_compare_exchange_n(&guard->backendRetained,&empty,1U,false,
        __ATOMIC_ACQ_REL,__ATOMIC_ACQUIRE))return;
    guard->backendBytes=bytes;
    auto *head=__atomic_load_n(&retainedBackendHead,__ATOMIC_ACQUIRE);
    do {guard->backendNext=head;}
    while(!__atomic_compare_exchange_n(&retainedBackendHead,&head,guard,false,
        __ATOMIC_RELEASE,__ATOMIC_ACQUIRE));
}
BackendSnapshot backendSnapshot() {
    BackendSnapshot out{};
    out.releaseRefusals=__atomic_load_n(&backendReleaseRefusals,__ATOMIC_RELAXED);
    for(auto *guard=__atomic_load_n(&retainedBackendHead,__ATOMIC_ACQUIRE);guard;guard=guard->backendNext){
        ++out.retainedObjects;out.retainedBytes+=guard->backendBytes;
        if(guard->backendIdentity.owner&&guard->backendIdentity.generation)++out.associatedObjects;
        else ++out.legacyObjects;
    }
    return out;
}
