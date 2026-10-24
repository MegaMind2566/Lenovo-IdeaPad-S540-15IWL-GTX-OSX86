#!/usr/bin/env python3
"""Host controls for graph identity/reuse; never substitute for native validation."""
import argparse
import ast
from collections import Counter
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


check = load('isolated_graph_reuse_controls', HERE / 'check.py')
budget = load('isolated_graph_reuse_budget', HERE / 'native_budget.py')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class Fixture:
    """Synthetic helper-only receipt fixture, not a successful native measurement."""
    def __init__(self, root):
        self.root, self.units, self.graphs = root, [], []
        self.inputs = {}
        for name in ('compiler', 'decoder', 'header.h', 'helper.py', 'composition.json', 'report.json'):
            path = root / name
            path.write_text('isolated input: ' + name)
            self.inputs[str(path)] = sha(path)
        self.argv = [str(root / 'decoder'), '--macho', '--disassemble']
        for index, size in enumerate((8, 0)):
            source, obj, capture = (root / ('unit%d' % index + suffix) for suffix in ('.c', '.o', '.stack.json'))
            source.write_text('int fixture_%d(void);\n' % index)
            obj.write_bytes(b'isolated synthetic object ' + bytes([index]))
            capture.write_text('{"host_fixture":true,"index":%d}\n' % index)
            for path in (source, obj, capture):
                self.inputs[str(path)] = sha(path)
            unit = dict(source=str(source), source_sha256=sha(source), object_sha256=sha(obj))
            image = SimpleNamespace(data=obj.read_bytes(), sections=[SimpleNamespace(name='__text', size=size)])
            self.units.append(dict(unit=unit, object=obj, capture=capture, image=image))
            self.graphs.append(dict(object=str(obj), object_sha256=sha(obj), source=str(source),
                source_sha256=sha(source), capture_sha256=sha(capture), nodes=[{'id':'fixture'}] if size else []))
        self.graph_path, self.result_path = root / 'current-object-graphs.json', root / 'results.json'
        self.graph_bytes = json.dumps(self.graphs, sort_keys=True).encode()
        self.graph_path.write_bytes(self.graph_bytes)
        self.prior = dict(status='complete-current-native-stack-graph-measured', host_fixture_only=True,
            complete_native_object_inventory=True, current_native_object_count=len(self.units),
            final_image_selection=None, context_review={'refinements': []}, profile_contract={'fixture': True},
            graph_path=str(self.graph_path), graph_sha256=sha(self.graph_path), decoder_command=self.argv,
            input_sha256={**self.inputs, str(self.graph_path):sha(self.graph_path)})
        self.result_path.write_text(json.dumps(self.prior, sort_keys=True))
        self.result_sha = sha(self.result_path)

    def bound(self):
        bound = check.Bindings()
        for path, digest in self.inputs.items():
            bound.file(path, digest)
        return bound

    def ledger(self):
        # Unit-test the private receipt consumer in isolation. No native gate,
        # compiler identity, source replay, or measure_verified_plan is mocked.
        return patch.dict(check._FRESH_MEASUREMENTS,
            {id(self.prior):(self.prior,self.result_path,self.result_sha)}, clear=True)

    def reuse(self, bound=None, prior=None):
        return check.reuse_current_graphs(self.prior if prior is None else prior,
            self.units, self.bound() if bound is None else bound, self.argv, {'fixture': True})

    def data(self, prior=None, raw=None, inputs=None, units=None, argv=None, contract=None):
        return check.checked_reuse_data(self.prior if prior is None else prior,
            self.graph_bytes if raw is None else raw, self.inputs if inputs is None else inputs,
            self.units if units is None else units, self.argv if argv is None else argv,
            {'fixture': True} if contract is None else contract)


class GraphReuseControls(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(prefix='s540-graph-reuse-')
        self.addCleanup(self.temp.cleanup)
        self.f = Fixture(Path(self.temp.name))

    def test_positive_fixture_repeats_collector_hashes_and_final_full_check(self):
        counts = Counter()
        original = check.stack.sha
        def counted(path):
            counts[str(path)] += 1
            return original(path)
        bound = self.f.bound()
        with self.f.ledger(), patch.object(check.stack, 'sha', counted):
            graphs, provenance = self.f.reuse(bound)
        self.assertEqual(graphs, self.f.graphs)
        self.assertEqual(provenance['decoder_processes_executed'], 0)
        self.assertEqual(counts[str(self.f.units[0]['object'])], 2)
        self.assertEqual(counts[str(self.f.units[1]['object'])], 1)
        for unit in self.f.units:
            self.assertEqual(counts[str(unit['capture'])], 1)
        self.assertEqual(set(bound.files), {*self.f.inputs, str(self.f.graph_path), str(self.f.result_path)})
        bound.unchanged()

    def test_no_receipt_and_equal_serialized_copy_cannot_authorize_reuse(self):
        with self.assertRaises(ValueError):
            self.f.reuse()
        with self.f.ledger(), self.assertRaises(ValueError):
            self.f.reuse(prior=deepcopy(self.f.prior))

    def test_separate_module_instance_has_no_authorizing_receipt(self):
        other = load('separate_graph_reuse_controls', HERE / 'check.py')
        with self.f.ledger(), self.assertRaises(ValueError):
            other.reuse_current_graphs(self.f.prior, self.f.units, self.f.bound(), self.f.argv, {'fixture': True})

    def test_changed_graph_rejected(self):
        self.f.graph_path.write_bytes(self.f.graph_bytes + b'\n')
        with self.f.ledger(), self.assertRaises(ValueError):
            self.f.reuse()

    def test_caller_rehash_of_graph_and_result_does_not_update_internal_receipt(self):
        with self.f.ledger():
            self.f.graph_path.write_bytes(self.f.graph_bytes + b'\n')
            self.f.prior['graph_sha256'] = sha(self.f.graph_path)
            self.f.prior['input_sha256'][str(self.f.graph_path)] = sha(self.f.graph_path)
            self.f.result_path.write_text(json.dumps(self.f.prior, sort_keys=True))
            with self.assertRaises(ValueError):
                self.f.reuse()

    def test_changed_original_result_object_rejected(self):
        with self.f.ledger():
            self.f.prior['caller_mutation'] = True
            with self.assertRaises(ValueError):
                self.f.reuse()

    def test_symlinked_graph_and_result_rejected(self):
        for path in (self.f.graph_path, self.f.result_path):
            saved = path.with_name(path.name + '.original')
            path.rename(saved)
            path.symlink_to(saved)
            try:
                with self.f.ledger(), self.assertRaises(ValueError):
                    self.f.reuse()
            finally:
                path.unlink()
                saved.rename(path)

    def test_complete_input_map_refuses_any_changed_missing_or_extra_binding(self):
        for key in self.f.inputs:
            with self.subTest(path=key):
                changed = dict(self.f.inputs, **{key:'0' * 64})
                with self.assertRaises(ValueError):
                    self.f.data(inputs=changed)
        for changed in ({k:v for k,v in self.f.inputs.items() if k != str(self.f.root/'compiler')},
                        dict(self.f.inputs, unexpected='0' * 64)):
            with self.assertRaises(ValueError):
                self.f.data(inputs=changed)

    def test_changed_decoder_arguments_or_profile_contract_rejected(self):
        for kwargs in ({'argv':self.f.argv+['--changed']}, {'contract':{'changed':True}}):
            with self.assertRaises(ValueError):
                self.f.data(**kwargs)

    def test_graph_hash_and_its_input_binding_both_required(self):
        with self.assertRaises(ValueError):
            self.f.data(raw=self.f.graph_bytes + b'\n')
        prior = deepcopy(self.f.prior)
        prior['input_sha256'][prior['graph_path']] = '0' * 64
        with self.assertRaises(ValueError):
            self.f.data(prior=prior)

    def test_missing_reordered_duplicate_or_changed_unit_rejected(self):
        for units in (self.f.units[:-1], list(reversed(self.f.units))):
            with self.assertRaises(ValueError):
                self.f.data(units=units)
        changed = deepcopy(self.f.graphs)
        changed[1] = deepcopy(changed[0])
        raw = json.dumps(changed).encode()
        prior = deepcopy(self.f.prior)
        prior['graph_sha256'] = hashlib.sha256(raw).hexdigest()
        prior['input_sha256'][prior['graph_path']] = prior['graph_sha256']
        with self.assertRaises(ValueError):
            self.f.data(prior=prior, raw=raw)
        for field in ('source_sha256', 'object_sha256'):
            units = deepcopy(self.f.units)
            units[0]['unit'][field] = '0' * 64
            with self.assertRaises(ValueError):
                self.f.data(units=units)

    def test_filtered_incomplete_or_pruned_preliminary_rejected(self):
        for change in ({'final_image_selection':{'already':'filtered'}},
                       {'complete_native_object_inventory':False},
                       {'context_review':{'refinements':['changed']}}):
            with self.assertRaises(ValueError):
                self.f.data(prior=dict(self.f.prior, **change))

    def test_object_file_memory_and_capture_changes_rejected(self):
        for kind in ('file', 'memory', 'capture'):
            with self.subTest(kind=kind), TemporaryDirectory(prefix='s540-graph-mutant-') as temp:
                f = Fixture(Path(temp)); bound = f.bound()
                if kind == 'file': f.units[0]['object'].write_bytes(b'changed object')
                elif kind == 'memory': f.units[0]['image'].data = b'changed parsed object'
                else: f.units[0]['capture'].write_bytes(b'changed capture')
                with f.ledger(), self.assertRaises(ValueError):
                    f.reuse(bound)

    def test_post_observation_object_mutation_rejected(self):
        original = check.stack.sha; bound = self.f.bound()
        def mutate(path):
            digest = original(path)
            if Path(path) == self.f.units[0]['capture']:
                self.f.units[0]['object'].write_bytes(b'changed after first observation')
            return digest
        with self.f.ledger(), patch.object(check.stack, 'sha', mutate), self.assertRaises(ValueError):
            self.f.reuse(bound)

    def test_final_full_check_covers_compiler_and_both_cache_files(self):
        for name in ('compiler', 'results.json', 'current-object-graphs.json'):
            with self.subTest(name=name), TemporaryDirectory(prefix='s540-graph-final-') as temp:
                f = Fixture(Path(temp)); bound = f.bound()
                with f.ledger(): f.reuse(bound)
                (f.root/name).write_bytes(b'changed after reuse')
                with self.assertRaises(ValueError): bound.unchanged()

    @unittest.skipIf(sys.platform == 'darwin', 'Actual non-Darwin gate control')
    def test_actual_native_entry_still_refuses_this_host_without_gate_mocks(self):
        with self.assertRaisesRegex(ValueError, 'requires Intel macOS|require.*Intel macOS'):
            check.measure_verified_plan(SimpleNamespace(), {}, lambda:{}, Path('absent'), Path('absent'))

    def test_original_validator_filter_and_root_implementations_unchanged(self):
        expected = {
            'Bindings':'37f6c0f30c32d006aced99cd4e9bccd4c344b51ffb02020ef11c7a0823e53b96',
            'checked_rows':'09b0248bfc562e8b1b8b2454fc06943fdeada1512494e5fb0ad8c5bc23e8ec3b',
            'select_final_graphs':'5135ceb8dc7e0242748e801d55526e9bd4a3a61f8085bad97939fa70f04cecdc',
            'selected_actual_roots':'3bcde642fddffc7cf95f04b377ac24af2ae984f959f93933828f94e102021b30',
            'verify_source_plan':'07eba103e7dfd30d46c75e3d46aa0767cadbb7c191feb374aba9581c61ea8943'}
        tree = ast.parse((HERE/'check.py').read_text())
        for name, digest in expected.items():
            node = next(n for n in tree.body if getattr(n,'name',None)==name)
            self.assertEqual(hashlib.sha256(ast.dump(node).encode()).hexdigest(), digest, name)
        function = next(n for n in tree.body if getattr(n,'name',None)=='measure_verified_plan')
        direct = [(n.value.func, n.lineno) for n in function.body if isinstance(n,ast.Expr) and isinstance(n.value,ast.Call)]
        unchanged = next(line for f,line in direct if isinstance(f,ast.Attribute) and f.attr=='unchanged')
        replay = max(line for f,line in direct if isinstance(f,ast.Name) and f.id=='verify_source_plan')
        written = max(line for f,line in direct if isinstance(f,ast.Name) and f.id=='write')
        registration = next(n.lineno for n in ast.walk(function) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Subscript) and isinstance(t.value,ast.Name) and t.value.id=='_FRESH_MEASUREMENTS' for t in n.targets))
        self.assertLess(unchanged,replay); self.assertLess(replay,written); self.assertLess(written,registration)


def actual_evidence(path):
    """Inspect historical native bytes as data; never authorize their live reuse."""
    pre_dir, final_dir = path/'image/preliminary-stack', path/'image/final-stack'
    prior = json.loads((pre_dir/'results.json').read_text())
    final = json.loads((final_dir/'results.json').read_text())
    raw = (pre_dir/'current-object-graphs.json').read_bytes()
    inputs = dict(prior['input_sha256']); assert inputs.pop(prior['graph_path']) == prior['graph_sha256']
    units = []
    for group,name in (('original','full-original-compilation'),('project','project-compilation')):
        report = json.loads((path/'native'/(name+'.json')).read_text())
        for row in report['results']:
            capture = row['stack_usage']; local = path/'native'/(group+'-objects')/Path(capture['path']).name
            unit = json.loads(local.read_text())
            assert sha(local)==capture['sha256']
            assert sha(path/'native'/(group+'-objects')/row['object'])==row['object_sha256']
            units.append(dict(unit=unit,object=Path(unit['object']),capture=Path(capture['path'])))
    graphs = check.checked_reuse_data(prior,raw,inputs,units,prior['decoder_command'],prior['profile_contract'])
    final_graph = final_dir/'current-object-graphs.json'
    assert sha(final_graph)==final['graph_sha256']
    image = path/'image'/Path(final['final_image_selection']['path']).name
    assert sha(image)==final['final_image_selection']['sha256']
    selected,selection = check.select_final_graphs(graphs,image,check.Bindings())
    assert selected==json.loads(final_graph.read_text())
    roots,local = {},{}
    for label,row in final['roots'].items():
        if row.get('root_lookup')=='source-scoped-local-node-id':
            local[label]=(row['source_scoped_local_node_id'],row['symbol'])
        else: roots[label]=row['symbol']
    resolved = check.selected_actual_roots(selected,roots,local)
    assert resolved['roots']==final['roots']
    assert budget.derive(dict(final,**resolved))==budget.derive(final)
    try: check.reuse_current_graphs(prior,units,check.Bindings(),prior['decoder_command'],prior['profile_contract'])
    except ValueError: pass
    else: raise AssertionError('Historical native report authorized live reuse')
    return dict(status='passed-historical-native-data-only',objects=len(units),
        original_graph_sha256=prior['graph_sha256'],final_graph_sha256=final['graph_sha256'],
        final_image_sha256=sha(image),selected_objects=len(selected),selected_nodes=sum(len(g['nodes']) for g in selected),
        same_final_graph_as_actual_second_decode=True,same_roots_and_budget=True,historical_live_reuse_refused=True,
        native_validation_performed=False,current_native_measurement_performed=False)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence',type=Path)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(GraphReuseControls))
    if not result.wasSuccessful(): raise SystemExit(1)
    report=dict(format=1,status='passed-graph-reuse-host-controls',host_control=True,native_validation_performed=False,
        host_tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),skipped=len(result.skipped),
        source_sha256={str(p.relative_to(HERE.parents[2])):sha(p) for p in (HERE/'check.py',HERE.parent/'prospective-experimental-image/link_native.py',Path(__file__))})
    if args.evidence: report['historical_native_data']=actual_evidence(args.evidence.resolve(strict=True))
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(report,sort_keys=True,indent=2)+'\n')
    print(json.dumps(report,sort_keys=True))


if __name__=='__main__': main()
