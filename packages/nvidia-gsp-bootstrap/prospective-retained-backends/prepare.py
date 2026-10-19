#!/usr/bin/env python3
"""Exact isolated successor retaining direct Darwin backend lifetimes.

Takes an existing complete composition, emits only changed project files.
No gate, private API, unload receipt, or physical final-release path is added.
"""
from pathlib import Path
import argparse
import hashlib
import json

HERE = Path(__file__).resolve().parent
RECORD = 'packages/nvidia-gsp-bootstrap/prospective-first-transaction/record/S540NvidiaGspFirstTransaction.c'
HEADER = RECORD[:-1]+'h'
BASE = 'packages/nvidia-darwin-services/src/'
INTERNAL = BASE+'S540NvidiaDarwinInternal.hpp'
PLATFORM = BASE+'S540NvidiaDarwinPlatform.cpp'
SYNC = BASE+'S540NvidiaDarwinSync.cpp'
TIMER = BASE+'S540NvidiaDarwinTimer.cpp'
WORK = BASE+'S540NvidiaDarwinWork.cpp'
PROCESS = BASE+'S540NvidiaDarwinProcess.cpp'
HOST = 'packages/nvidia-global-rm/src/S540NvidiaGlobalRmHost.cpp'
INPUTS = (RECORD, HEADER, INTERNAL, PLATFORM, SYNC, TIMER, WORK, PROCESS, HOST)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('Exact retained backend anchor missing or ambiguous: '+old[:100])
    return text.replace(old, new)


def transforms(values):
    out = dict(values)
    out[RECORD] = once(out[RECORD], 'SITE_HOST=9', 'SITE_HOST=9, SITE_BACKEND=10')
    anchor = 'static NvU64 lastEpoch;'
    out[RECORD] = once(out[RECORD], anchor,
        'static NvU32 backendScopes;\n'
        'static struct { NvU64 id,thread; } backendPermits[CAPACITY];\n'+anchor)
    anchor = 'NV_STATUS s540FirstTxnBeginOwner('
    out[RECORD] = once(out[RECORD], anchor, (HERE/'record-api.c.inc').read_text()+'\n'+anchor)
    out[RECORD] = once(out[RECORD],
        'if(!__atomic_compare_exchange_n(&record.phase,&empty,~0U,NV_FALSE,\n'
        '        __ATOMIC_ACQ_REL,__ATOMIC_ACQUIRE))return NV_ERR_IN_USE;',
        'if(!__atomic_compare_exchange_n(&record.phase,&empty,~0U,NV_FALSE,\n'
        '        __ATOMIC_SEQ_CST,__ATOMIC_SEQ_CST))return NV_ERR_IN_USE;')
    anchor = '    status=s540GlobalRmHostRetentionPreflight();'
    out[RECORD] = once(out[RECORD], anchor, '''    /* The reservation closes new backend scopes before this read. Do not
     * publish an epoch over a preowner physical lifecycle operation, including
     * when another real refusal has already changed phase to RETAINED. */
    if(__atomic_load_n(&backendScopes,__ATOMIC_SEQ_CST)) {
        empty=~0U;
        (void)__atomic_compare_exchange_n(&record.phase,&empty,(NvU32)S540_FIRST_UNBOUND,NV_FALSE,
            __ATOMIC_ACQ_REL,__ATOMIC_ACQUIRE);
        return first()!=NV_OK?first():NV_ERR_BUSY_RETRY;
    }
'''+anchor)
    anchor = 'NV_STATUS s540FirstTxnHostCaptureAllocation('
    out[HEADER] = once(out[HEADER], anchor, '''/* Direct backend lifecycle permits are actual record-owned thread scopes.
 * Empty birth identity is allowed only before BeginOwner; never retagged.
 * Bound epochs categorically refuse physical release, even after sticky. */
NV_STATUS s540FirstTxnBackendBegin(S540FirstTxnHostIdentity *, NvU64 *permit);
NV_STATUS s540FirstTxnBackendEnd(NvU64 permit);
NV_STATUS s540FirstTxnBackendBeginRelease(const S540FirstTxnHostIdentity *, NvU64 *permit);
'''+anchor)
    anchor = '#include "S540NvidiaDarwinServices.h"'
    out[INTERNAL] = once(out[INTERNAL], anchor, anchor+'\n#include "../../nvidia-gsp-bootstrap/prospective-first-transaction/record/S540NvidiaGspFirstTransaction.h"')
    out[INTERNAL] = once(out[INTERNAL], 'struct Guard {', '''struct Guard {
    S540FirstTxnHostIdentity backendIdentity;
    Guard *backendNext;
    NvU32 backendRetained,backendBytes,backendParts;
''')
    anchor = 'struct GuardObject { Guard guard; };'
    out[INTERNAL] = once(out[INTERNAL], anchor, (HERE/'internal.hpp.inc').read_text()+'\n'+anchor)
    out[INTERNAL] = once(out[INTERNAL], '''    auto *object = static_cast<T *>(allocate(sizeof(T)));
    if (object == nullptr) return nullptr;
    if (!object->guard.init()) { deallocate(object, sizeof(T)); return nullptr; }
    account(1);''', '''    BackendConstruction construction;
    if(!construction.allowed())return nullptr;
    auto *object = static_cast<T *>(allocate(sizeof(T)));
    if (object == nullptr) return nullptr;
    object->guard.backendIdentity=construction.identity;
    object->guard.backendBytes=sizeof(T);
    account(1);
    if (!object->guard.init()) {
        BackendFinalizer release(object->guard,sizeof(T));
        if(release.allowed()){object->guard.dispose();deallocate(object,sizeof(T));account(-1);}
        return nullptr;
    }''')
    out[INTERNAL] = once(out[INTERNAL], 'template <typename T> void destroy(T *object) {',
        'template <typename T> void destroy(T *object) {\n'
        '    BackendFinalizer release(object->guard,sizeof(T));\n'
        '    if(!release.allowed())return;')
    out[PLATFORM] = once(out[PLATFORM], 'namespace S540DarwinInternal {',
        'namespace S540DarwinInternal {\n'+(HERE/'platform.cpp.inc').read_text())
    out[PLATFORM] = once(out[PLATFORM], '    return value != nullptr;',
        '    if(value!=nullptr)backendParts=1;\n    return value != nullptr;')
    out[PLATFORM] = once(out[PLATFORM], '    if (pthread_cond_init(&changed, nullptr) != 0) {\n'
        '        if (pthread_mutex_destroy(&value) != 0) violation("native guard unwind");\n'
        '        return false;\n    }\n    return true;',
        '    backendParts=1;\n'
        '    if (fail(4) || pthread_cond_init(&changed, nullptr) != 0)return false;\n'
        '    backendParts=3;\n    return true;')
    out[PLATFORM] = once(out[PLATFORM], '    IOSimpleLockFree(value);',
        '    if(backendParts&1)IOSimpleLockFree(value);')
    out[PLATFORM] = once(out[PLATFORM], '''    if (pthread_cond_destroy(&changed) != 0 || pthread_mutex_destroy(&value) != 0)
        violation("native guard destruction before quiescence");''',
        '''    if ((backendParts&2) && pthread_cond_destroy(&changed) != 0)
        violation("native condition destruction before quiescence");
    if ((backendParts&1) && pthread_mutex_destroy(&value) != 0)
        violation("native mutex destruction before quiescence");''')
    # Whole public thread-call construction is covered, not only allocation.
    for name, typename, action in ((TIMER,'S540DarwinTimer','timer'), (WORK,'os_work_queue','queue')):
        anchor = '    auto *'+action+' = create<'+typename+'>();'
        out[name] = once(out[name], anchor,
            '    BackendConstruction construction;\n'
            '    if(!construction.allowed())return NV_ERR_NOT_READY;\n'+anchor)
        anchor = 'extern "C" void s540Darwin'+('TimerDestroy(S540DarwinTimer *timer)' if name==TIMER else 'WorkQueueDestroy(os_work_queue *queue)')+' {\n'
        anchor += '    if ('+action+' == nullptr) return;'
        out[name] = once(out[name], anchor, anchor+'\n'
            '    BackendFinalizer release('+action+'->guard,sizeof(*'+action+'));\n'
            '    if(!release.allowed())return;')
    # Refuse before even checking quiescence: a held lock remains held and usable.
    for typename, name in [('Semaphore','mutex'), ('GuardObject','spinlock'),
            ('Semaphore','semaphore'), ('RwLock','rwlock')]:
        anchor = 'extern "C" void NV_API_CALL s540Darwin_os_free_'+name+'(void *handle) {\n    if (handle == nullptr) return;'
        out[SYNC] = once(out[SYNC], anchor, anchor+'\n'
            '    BackendFinalizer release(static_cast<'+typename+' *>(handle)->guard,sizeof('+typename+'));\n'
            '    if(!release.allowed())return;')
    anchor = 'extern "C" void NV_API_CALL s540Darwin_os_free_wait_queue(os_wait_queue *object) {\n    if (object == nullptr) return;'
    out[SYNC] = once(out[SYNC], anchor, anchor+'\n'
        '    BackendFinalizer release(object->guard,sizeof(*object));\n'
        '    if(!release.allowed())return;')
    # The only other direct allocator caller is the public PID reference.
    # Keep its proc reference as well as storage on retained final release.
    out[PROCESS]=once(out[PROCESS], 'struct PidInfo {',
        'struct PidInfo {\n    S540DarwinInternal::Guard guard;')
    out[PROCESS]=once(out[PROCESS],
        'static_cast<PidInfo *>(S540DarwinInternal::allocate(sizeof(PidInfo)))',
        'S540DarwinInternal::create<PidInfo>()')
    out[PROCESS]=once(out[PROCESS], '        S540DarwinInternal::deallocate(info, sizeof(PidInfo));',
        '        S540DarwinInternal::destroy(info);')
    out[PROCESS]=once(out[PROCESS], '    S540DarwinInternal::account(1);\n    return info;',
        '    return info;')
    anchor='    auto *info = static_cast<PidInfo *>(handle);'
    out[PROCESS]=once(out[PROCESS],anchor,anchor+'\n'
        '    S540DarwinInternal::BackendFinalizer release(info->guard,sizeof(*info));\n'
        '    if(!release.allowed())return;')
    out[PROCESS]=once(out[PROCESS],
        '    S540DarwinInternal::deallocate(info, sizeof(PidInfo));\n    S540DarwinInternal::account(-1);',
        '    S540DarwinInternal::destroy(info);')
    anchor='extern "C" NvBool s540GlobalRmHostShutdown(void)\n{'
    out[HOST]=once(out[HOST],anchor,anchor+'''
    /* Heap counters alone cannot authorize release of the Host guard/facts.
     * The actual permanent owner (including reservation and sticky failure)
     * categorically closes this path, even with zero tracked allocations. */
    struct BackendHostRelease {
        NvU64 permit=0;
        ~BackendHostRelease() {
            if(permit && s540FirstTxnBackendEnd(permit)!=NV_OK)__builtin_trap();
        }
    } backendRelease;
    const S540FirstTxnHostIdentity unassociated={nullptr,0};
    if(s540FirstTxnBackendBeginRelease(&unassociated,&backendRelease.permit)!=NV_OK)return NV_FALSE;
''')
    return out


def prepare(composition, output):
    composition=composition.resolve(strict=True)
    manifest=json.loads(composition.read_text())
    if manifest.get('status')!='materialized-source-only':
        raise ValueError('Complete source-only composition required')
    project=(composition.parent/manifest['project']).resolve(strict=True)
    output=output.resolve()
    if output.exists() or output.is_relative_to(project) or project.is_relative_to(output):
        raise ValueError('Fresh output outside input project required')
    values={};inputs={}
    for name in INPUTS:
        path=project/name
        expected=manifest['project_files'][name]['sha256']
        if path.is_symlink() or sha(path)!=expected:
            raise ValueError('Composed input changed: '+name)
        values[name]=path.read_text();inputs[name]=expected
    changed=transforms(values)
    output.mkdir(parents=True)
    rows={}
    for name,value in changed.items():
        path=output/'project'/name
        path.parent.mkdir(parents=True,exist_ok=True);path.write_text(value)
        rows[name]={'source':path.relative_to(output).as_posix(),
            'input_sha256':inputs[name],'output_sha256':sha(path)}
    if any(sha(project/name)!=value for name,value in inputs.items()):
        raise ValueError('Input changed during backend preparation')
    report={'format':1,'sources':rows,'composition_sha256':sha(composition),
        'mode':'retained-direct-darwin-backends','retained_after_actual_begin_owner':True,
        'physical_free_for_associated_epoch':False,'preowner_retained_not_retagged':True,
        'first_error_cleared':False,'stop_receipt_issued':False,'final_release_issued':False,
        'hardware_admission':False,'original_entry_admission':False,'production_candidate_allowed':False}
    (output/'project-successor.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--composition',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps({'status':'prepared-retained-backends-source',
        'files':len(prepare(args.composition,args.output)['sources']),'hardware_admission':False}))
