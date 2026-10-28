"""Negative controls for the actual topology engine source."""
MUTATIONS = {'foreign-owner-accepted': ('state.owner == owner', 'owner != nullptr'),
 'wrong-bridge-class': ('classSubclass != 0x0604U', 'false'),
 'non-Intel-host': ('NvU16(identity) != 0x8086U', 'false'),
 'wrong-bridge-header': ('header != 1U', 'false'),
 'wrong-host-header': ('header != 0U', 'false'),
 'wrong-primary-bus': ('primary != candidate.bus', 'false'),
 'missing-secondary-chain': ('NvU8(record.buses >> 8U) != downstreamBus', 'false'),
 'candidate-domain-ignored': ('!candidate.resource || candidate.segment != segment ||',
                              '!candidate.resource || false ||'),
 'duplicate-address-accepted': ('sameAddress(candidate, candidates[previous])',
                                '(sameAddress(candidate, candidates[previous]) && '
                                'candidate.segment == ~0U)'),
 'root-extended-offset-accepted': ('record.candidate.rootConfig && (offset >= 256U || width > 256U '
                                   '- offset)',
                                   'record.candidate.rootConfig && (offset >= 4096U || width > '
                                   '4096U - offset)'),
 'lookup-reads-before-match': ('if (!ready(state, owner)) return nullptr;',
                               'if (!ready(state, owner)) return nullptr;\n'
                               '    (void)revalidate(state, state.records[0], false);'),
 'lost-critical-read-status': ('if (status != NV_OK) return status;\n'
                               '    return identity == record.identity',
                               'if (status != NV_OK) return NV_OK;\n'
                               '    return identity == record.identity'),
 'lost-post-read-revalidation': ('        status = revalidate(state, record, i + 1U == '
                                 'state.count);\n'
                                 '        if (status != NV_OK) return status;\n'
                                 '        value = captured;',
                                 '        value = captured;'),
 'generation-reused-after-clear': ('void clear(State &state) { state = State{}; }',
                                   'void clear(State &state) { state = State{}; lastGeneration = '
                                   '0U; }'),
 'bad-FHB-reference-accepted': ('!matches(state.records[state.count - 1U], facts.fhb)', 'false'),
 'bad-upstream-reference-accepted': ('!matches(state.records[0], facts.upstream)', 'false'),
 'bad-chipset-reference-accepted': ('return chipset ? NV_OK : NV_ERR_INVALID_DATA;',
                                    '(void)chipset; return NV_OK;')}
