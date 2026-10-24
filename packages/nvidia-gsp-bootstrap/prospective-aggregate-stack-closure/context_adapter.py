#!/usr/bin/env python3
"""Current source/receiver review without importing historical graph rewrites."""
from pathlib import Path
import hashlib
import json

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
RECEIVERS = (
    ('packages/nvidia-darwin-services/src/S540NvidiaDarwinTimer.cpp',
     ('S540DarwinTimerAction action;', 'void *context;', 'timer->action(timer->context);')),
    ('packages/nvidia-darwin-services/src/S540NvidiaDarwinWork.cpp',
     ('S540DarwinWorkAction action;', 'void *context;', 'queue->action(queue->context, data);')),
    ('packages/nvidia-gsp-bootstrap/src/S540NvidiaGspDispatcher.cpp',
     ('self->action = action; self->context = context;',
      'const NV_STATUS status = self->action(self->context, item.command);',
      'kernel_thread_start(Impl::entry, self, &self->worker)')),
    ('packages/nvidia-gsp-bootstrap/src/S540NvidiaGspBootstrap.cpp',
     ('impl_->dispatcher.start(Impl::action, impl_)', 'static NV_STATUS action(void *owner, NvU32 command)')),
    ('packages/nvidia-device-transport/src/S540NvidiaDarwinDevice.cpp',
     ('p->interrupt=contract;', 'p->bottomHalf.initialize(bottomHalf,p)',
      'p->provider->registerInterrupt(static_cast<int>(p->irqSource),p->owner,interrupt,p)',
      'p->interrupt.top(p->interrupt.context,locked,unlocked)')),
)
IRQ_BINDING = 'packages/nvidia-gsp-bootstrap/prospective-irq-installation/S540NvidiaGspIrqInstallation.hpp'


def require(value, reason):
    if not value:
        raise ValueError(reason)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def native_context_contract(args, value):
    composition = Path(args.composition).resolve(strict=True)
    bindings = {}
    for path in (Path(__file__), HERE / 'check.py', HERE / 'native_budget.py', HERE / 'SOURCE-CONTRACT.json'):
        relative = path.relative_to(ROOT).as_posix()
        require(value['retained_trial']['helper_source_sha256'].get(relative) == sha(path),
                'Current graph/context helper is absent from the replayed source contract: ' + relative)
        bindings[str(path)] = sha(path)
    for relative, tokens in RECEIVERS:
        path = composition / 'project' / relative
        expected = value['project_files'][relative]['sha256']
        require(sha(path) == expected, 'Actual callback receiver source changed')
        text = path.read_text()
        require(all(token in text for token in tokens), 'Actual receiver/callback layout changed: ' + relative)
        bindings[str(path)] = expected
    binding = composition / 'project' / IRQ_BINDING
    require(sha(binding) == value['project_files'][IRQ_BINDING]['sha256'] and
        'this,top,locked,unlocked,mask,ready,identity_.nv,selectMode,validate' in binding.read_text(),
        'Actual retained typed interrupt-contract construction changed')
    bindings[str(binding)] = sha(binding)
    contract = {'format': 1, 'scope': 'current-native-retained-experiment-context-review',
        'source_composition_sha256': sha(composition / 'composition.json'),
        'input_sha256': bindings, 'historical_graphs_transferred': False,
        'receiver_layout_reviewed_against_actual_current_source': True,
        'known_registered_callback_prefixes_budgeted_separately': True,
        'indirect_receiver_target_sets_proven': False, 'context_edges_pruned': 0,
        'unknown_receiver_aliases_remain_barriers': True,
        'formal_stack_bound_proven': False}

    def review(current_args, current_value, graphs):
        require(current_value == value and Path(current_args.composition).resolve(strict=True) == composition,
                'Context callback belongs to another native source plan')
        for path, digest in bindings.items():
            require(sha(path) == digest, 'Current context review input changed')
        sources = {g['source'] for g in graphs}
        require(all(str(composition / 'project' / name) in sources for name, _ in RECEIVERS),
                'Current receiver objects were omitted from the fresh complete graph')
        return dict(contract, status='current-receivers-reviewed-unknown-aliases-retained', refinements=[])

    return {'profile_contract': contract, 'context_review_callback': review}
