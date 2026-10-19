#!/usr/bin/env python3
"""Pin associated Host backing for one no-reclaim diagnostic source profile.

No operation in this successor authorizes GPU entry, hardware stop or unload.
The exact generated input project is required; changes are emitted separately.
"""
from pathlib import Path
import argparse
import hashlib
import json

RECORD = 'packages/nvidia-gsp-bootstrap/prospective-first-transaction/record/S540NvidiaGspFirstTransaction.c'
HEADER = RECORD[:-1]+'h'
HOST = 'packages/nvidia-global-rm/src/S540NvidiaGlobalRmHost.cpp'
RETENTION = 'packages/nvidia-global-rm/src/S540NvidiaGlobalRmHostRetention.h'
RETENTION_ORIGIN = 'packages/nvidia-gsp-bootstrap/prospective-host-retention/S540NvidiaGlobalRmHostRetention.h'
API = '''NV_STATUS s540FirstTxnHostRetainDiagnostic(const S540FirstTxnHostIdentity *identity, NvBool *retain) {
    if(!identity || !retain)return NV_ERR_INVALID_ARGUMENT;
    *retain=NV_FALSE;
    if(!bound())return LD(&record.phase)!=S540_FIRST_UNBOUND?NV_ERR_NOT_READY:
        (!identity->owner&&!identity->generation?NV_ERR_OBJECT_NOT_FOUND:NV_ERR_INVALID_STATE);
    if(identity->owner!=LD(&record.owner)||identity->generation!=LD(&record.generation)||!authorized())
        return refuse(NV_ERR_INVALID_STATE,SITE_HOST);
    if(first()!=NV_OK)return first();
    /* Fixed diagnostic policy: never issue a physical-free permit for the
     * bound epoch. A logical free retires its exact allocator record instead.
     * This does not assert object, queue, IRQ or device-DMA quiescence. */
    *retain=NV_TRUE;return NV_OK;
}
'''
HOST_RETIRE = '''    NvBool diagnosticRetain = NV_FALSE;
    const NV_STATUS diagnostic = s540FirstTxnHostRetainDiagnostic(&saved.identity, &diagnosticRetain);
    if (diagnostic == NV_OK && diagnosticRetain) {
        lock();
        if (records[slot].pointer != pointer || records[slot].serial != saved.serial || !records[slot].pending) {
            unlock(); noteInvalidFree(); return;
        }
        records[slot].pending = false;
        records[slot].retired = true;
        --retention.pendingFrees;
        ++retention.retiredAllocations;
        retention.retiredBytes += saved.bytes;
        ++retention.diagnosticRetiredAllocations;
        retention.diagnosticRetiredBytes += saved.bytes;
        unlock();
        return;
    }
'''


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('Exact diagnostic source anchor missing or ambiguous: '+old[:90])
    return text.replace(old, new)


def transforms(values):
    result = dict(values)
    anchor = 'NV_STATUS s540FirstTxnHostAcquireFree('
    result[RECORD] = once(result[RECORD], anchor, API+'\n'+anchor)
    result[HEADER] = once(result[HEADER], anchor,
        'NV_STATUS s540FirstTxnHostRetainDiagnostic(const S540FirstTxnHostIdentity *, NvBool *);\n'+anchor)
    anchor = '    S540FirstTxnHostFreePermit permit = 0;'
    result[HOST] = once(result[HOST], anchor, HOST_RETIRE+anchor)
    anchor = 'typedef struct S540GlobalRmHostRetentionSnapshot {'
    # Put explicitly separate counters in the retained-backing snapshot.
    for name in (RETENTION, RETENTION_ORIGIN):
        result[name] = once(result[name], anchor,
            anchor+'\n    NvU64 diagnosticRetiredAllocations, diagnosticRetiredBytes;')
    return result


def prepare(composition, output):
    composition = composition.resolve(strict=True)
    manifest = json.loads(composition.read_text())
    if manifest.get('status') != 'materialized-source-only':
        raise ValueError('Exact complete first-transaction composition required.')
    project = (composition.parent/manifest['project']).resolve(strict=True)
    output = output.resolve()
    if output.exists() or output.is_relative_to(project) or project.is_relative_to(output):
        raise ValueError('Fresh output outside the composed input project required.')
    values, inputs = {}, {}
    for name in (RECORD, HEADER, HOST, RETENTION, RETENTION_ORIGIN):
        path = project/name
        expected = manifest['project_files'][name]['sha256']
        if path.is_symlink() or sha(path) != expected:
            raise ValueError('Composed diagnostic input changed: '+name)
        inputs[name] = expected
        values[name] = path.read_text()
    changed = transforms(values)
    output.mkdir(parents=True)
    rows = {}
    for name, text in changed.items():
        target = output/'project'/name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
        rows[name] = {'input_sha256': inputs[name], 'output_sha256': sha(target),
                      'source': target.relative_to(output).as_posix()}
    if any(sha(project/name) != digest for name, digest in inputs.items()):
        raise ValueError('Input project changed during diagnostic preparation.')
    report = {'format': 1, 'sources': rows, 'mode': 'retained-no-reclaim-diagnostic',
              'composition_sha256': sha(composition),
              'physical_free_for_associated_epoch': False,
              'first_error_cleared': False, 'stop_receipt_issued': False,
              'final_release_issued': False, 'hardware_admission': False,
              'original_entry_admission': False, 'production_candidate_allowed': False}
    (output/'project-successor.json').write_text(json.dumps(report, indent=2, sort_keys=True)+'\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--composition', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = prepare(args.composition, args.output)
    print(json.dumps({'status': 'prepared-retained-diagnostic-source', 'files': len(result['sources']),
                      'hardware_admission': False}))
