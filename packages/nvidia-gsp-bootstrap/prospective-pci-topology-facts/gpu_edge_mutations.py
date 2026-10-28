"""Negative controls for actual Darwin GPU-edge helper bodies."""
MUTATIONS = {
    'precheck-removed': ('NV_STATUS status = verifyTopologyGpu(p, snapshot);', 'NV_STATUS status = NV_OK;'),
    'postcheck-removed': ('return verifyTopologyGpu(p, snapshot);', 'return NV_OK;'),
    'GPU-identity-ignored': ('identity == 0x1f9110deU', '((void)identity, true)'),
    'GPU-full-class-revision-ignored': ('revision == 0x030000a1U', '((void)revision, true)'),
    'GPU-subsystem-ignored': ('subsystem == 0x380617aaU', '((void)subsystem, true)'),
    'GPU-bus-ignored': ('provider->getBusNumber() == snapshot.bus', 'true'),
    'GPU-device-ignored': ('provider->getDeviceNumber() == snapshot.device', 'true'),
    'GPU-function-ignored': ('provider->getFunctionNumber() == snapshot.function', 'true'),
    'engine-error-precedence-lost': (
        'status = S540NvidiaPciTopology::validate(p->topology, owner, facts);\n    if (status != NV_OK) return status;',
        'status = S540NvidiaPciTopology::validate(p->topology, owner, facts);\n    (void)status;'),
}
