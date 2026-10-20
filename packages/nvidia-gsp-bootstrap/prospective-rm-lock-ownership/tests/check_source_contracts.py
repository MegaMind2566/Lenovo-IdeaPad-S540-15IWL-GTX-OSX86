#!/usr/bin/env python3
"""Strict source/profile binding tests, separate from CPU observation fixtures."""
import argparse
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

HERE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(HERE))
from prepare import REPO,body,inventory,sha,verify_bindings,verify_inventory,validate_output
parser=argparse.ArgumentParser()
parser.add_argument('--upstream',type=Path,required=True)
parser.add_argument('--v3-root',type=Path,required=True)
args,other=parser.parse_known_args()
contract=json.loads((HERE/'SOURCE-CONTRACT.json').read_text())

class SourceContracts(unittest.TestCase):
    def test_exact_sources_and_candidate(self):
        verify_bindings(args.upstream,contract['original_sources'])
        verify_bindings(args.v3_root,contract['v3_sources'])
        verify_bindings(HERE,contract['candidate_sources'])
        verify_bindings(REPO,contract['project_dependencies'])
    def test_real_legacy_bodies_unchanged(self):
        path='src/nvidia/arch/nvalloc/unix/src/os.c'
        for name,result in [('osAcquireRmSema','NV_STATUS'),('osCondAcquireRmSema','NV_STATUS'),('osReleaseRmSema','void')]:
            self.assertEqual(body((args.upstream/path).read_text(),name,result),
                body((args.v3_root/path).read_text(),name,result))
            self.assertEqual(sha(body((args.upstream/path).read_text(),name,result).encode()),contract['legacy_complete_body_sha256'][name])
    def test_actual_basic_and_tls_profile(self):
        basic=(args.v3_root/'src/nvidia/generated/rmconfig.h').read_text()
        self.assertIn('#define RMCFG_FEATURE_RM_BASIC_LOCK_MODEL         1',basic)
        tls=(args.v3_root/'src/nvidia/src/libraries/tls/tls.c').read_text()
        self.assertIn('tlsDatabase.lastEntryId = TLS_ENTRY_ID_DYNAMIC;',tls)
        self.assertIn('return portAtomicExIncrementU64(&tlsDatabase.lastEntryId);',body(tls,'tlsEntryAlloc','NvU64'))
        macro=(args.v3_root/'src/nvidia/generated/g_os_nvoc.h').read_text()
        for exact in ['#define osAllocRmSema(s)         (NV_OK)',
                '#define osFreeRmSema(s)','#define osIsRmSemaOwner(s)       (NV_TRUE)']:
            self.assertIn(exact,macro)
    def test_changed_original_file_refused(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);relative='src/nvidia/arch/nvalloc/unix/src/os.c'
            target=root/relative;target.parent.mkdir(parents=True)
            text=(args.upstream/relative).read_text()
            target.write_text(text.replace('NV_STATUS osAcquireRmSema(void *pSema)','NV_STATUS changedRmSema(void *pSema)',1))
            with self.assertRaisesRegex(ValueError,'Pinned source changed'):
                verify_bindings(root,{relative:contract['original_sources'][relative]})
    def test_changed_v3_or_getter_refused(self):
        observed=inventory(args.v3_root)
        verify_inventory(observed,contract['v3_tree_sha256'])
        changed=copy.deepcopy(observed);next(iter(changed.values()))['sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'Full immutable V3'):
            verify_inventory(changed,contract['v3_tree_sha256'])
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);relative='original-gpu-query.inc'
            (root/relative).write_text((HERE/relative).read_text().replace('_rmGpuAllocLockIsOwner()','NV_FALSE'))
            with self.assertRaisesRegex(ValueError,'Pinned source changed'):
                verify_bindings(root,{relative:contract['candidate_sources'][relative]})
    def test_pinned_source_symlink_refused_even_for_same_bytes(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'real.c').write_text('same bytes\n')
            (root/'alias.c').symlink_to('real.c')
            with self.assertRaisesRegex(ValueError,'source symlinks are not admitted'):
                verify_bindings(root,{'alias.c':sha(b'same bytes\n')})
    def test_standalone_output_refusals_precede_source_writes(self):
        roots=[HERE,args.upstream,args.v3_root,args.v3_root.parent/'project-overlay']
        for root in roots:
            with self.subTest(root=str(root)):
                proposed=root/'lock-ownership-output-must-not-exist'
                self.assertFalse(proposed.exists())
                with self.assertRaisesRegex(ValueError,'Output overlaps source input'):
                    validate_output(args.upstream,args.v3_root,proposed)
                self.assertFalse(proposed.exists())
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError,'Fresh output directory required'):
                validate_output(args.upstream,args.v3_root,Path(d))

if __name__=='__main__':unittest.main(argv=[sys.argv[0],*other])
