#!/usr/bin/env python3
"""Build one complete first-transaction development image; never install/load it.

Default execution requires Intel macOS and the Apple compiler/linker. Linux may
validate an exact source/SDK/firmware plan with --plan-only; it never receives a
linked-image success. The output has no .kext directory, Info.plist or package.
All runtime admission gates remain closed in every successful report.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import platform
import re
import shutil
import struct
import subprocess
import sys
import tempfile

import build_nvidia_execution as execution
import build_nvidia_transport as transport
import compile_nvidia_global_rm as original
import compose_nvidia_first_transaction as composition
import embed_nvidia_firmware as firmware
import nvidia_combined_metaclasses as combined_metaclasses
import nvidia_metaclass_initializers as metaclass

ROOT = Path(__file__).resolve().parents[1]
GSP = ROOT / 'packages/nvidia-gsp-bootstrap'
LOADER = GSP / 'prospective-loader'
LOADER_CONTRACT_SHA = 'df58185064d2cb5945feb3481a1023c09399b3fa6fabaee04a8ab351ffce86f8'
PLATFORM_SOURCE = 'packages/nvidia-gsp-bootstrap/prospective-platform-closure/S540ProspectivePlatformClosure.c'
PLATFORM_DEFINITIONS = {'S540_NVIDIA_DARWIN_PLATFORM_CLOSURE': '1',
    'NV_SUPPORTS_PLATFORM_DEVICE': '0', 'NV_SUPPORTS_PLATFORM_DISPLAY_DEVICE': '0'}
GATES = {'original_entry_admission': False, 'production_candidate_allowed': False,
         'hardware_admission': False, 'kernel_execution': 'not_tested',
         'gpu_access': False, 'module_loaded': False, 'installable_bundle_created': False}
ROOTS = tuple('RmDestroyRegistry RmPackageRegistry RmReadRegistryDword RmShutdownRm '
              'RmWriteRegistryDword coreInitializeRm rm_acquire_api_lock rm_acquire_gpu_lock '
              'rm_destroy_event_locks rm_disable_adapter rm_execute_work_item rm_free_private_state '
              'rm_gpu_handle_mmu_faults rm_init_adapter rm_init_event_locks rm_init_private_state '
              'rm_is_supported_device rm_isr rm_isr_bh rm_isr_bh_unlocked rm_release_api_lock '
              'rm_release_gpu_lock rm_run_nano_timer_callback rm_run_rc_callback '
              'rm_shutdown_adapter'.split())
LOADER_OPERATION_REFERENCE = r'''// SPDX-License-Identifier: MIT
// Independent actual SDK operations required by the closed loader backend.
#include <IOKit/IOService.h>
#include <IOKit/IOUserClient.h>
#include <libkern/c++/OSMetaClass.h>
extern "C" IOReturn s540SdkLoaderPrivilege(void *task) {
    return IOUserClient::clientHasPrivilege(task,kIOClientPrivilegeAdministrator);
}
extern "C" uint64_t s540SdkLoaderRegistryIdentity(IORegistryEntry *entry) {
    return entry->getRegistryEntryID();
}
extern "C" IOService *s540SdkLoaderResources(void) {
    return IOService::getResourceService();
}
extern "C" unsigned int s540SdkLoaderInstances(const OSMetaClass *meta) {
    return meta->getInstanceCount();
}
extern "C" bool s540SdkLoaderBaseClientStart(IOUserClient *client,IOService *provider) {
    return client->IOUserClient::start(provider);
}
'''


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Image:
    """Read actual thin Intel Mach-O nlists, including locals and n_desc flags."""
    def __init__(self, path: Path, expected_type: int):
        self.path, self.data = path, path.read_bytes()
        if len(self.data) < 32:
            raise ValueError('Truncated development image: ' + str(path))
        magic, cpu, _, kind, count, length, _, _ = struct.unpack_from('<8I', self.data)
        if (magic, cpu, kind) != (0xfeedfacf, 0x01000007, expected_type):
            raise ValueError('Expected thin x86_64 Mach-O type ' + str(expected_type))
        if length > len(self.data) - 32:
            raise ValueError('Truncated development image load commands')
        self.kind, self.sections, self.symbols = kind, [], []
        position, table = 32, None
        for _ in range(count):
            if position + 8 > 32 + length:
                raise ValueError('Truncated development load command')
            command, size = struct.unpack_from('<II', self.data, position)
            if size < 8 or position + size > 32 + length:
                raise ValueError('Invalid development load-command bounds')
            if command in original.DYLIB_LOAD_COMMANDS:
                raise ValueError('A development kernel image must not link a dylib')
            if command == 0x19:
                if size < 72:
                    raise ValueError('Truncated development segment')
                section_count = struct.unpack_from('<I', self.data, position + 64)[0]
                if 72 + 80 * section_count > size:
                    raise ValueError('Truncated development section list')
                for index in range(section_count):
                    raw = struct.unpack_from('<16s16sQQIIIIIIII', self.data,
                                             position + 72 + 80 * index)
                    section = {'name': raw[0].split(b'\0', 1)[0].decode('ascii'),
                        'segment': raw[1].split(b'\0', 1)[0].decode('ascii'),
                        'address': raw[2], 'size': raw[3], 'offset': raw[4],
                        'relocation_offset': raw[6], 'relocation_count': raw[7], 'flags': raw[8]}
                    if section['flags'] & 0xff not in (1, 0xc, 0x12):
                        if section['offset'] + section['size'] > len(self.data):
                            raise ValueError('Truncated development section bytes')
                    self.sections.append(section)
            elif command == 2:
                if table is not None or size != 24:
                    raise ValueError('Invalid development nlist command')
                table = struct.unpack_from('<4I', self.data, position + 8)
            position += size
        if position != 32 + length:
            raise ValueError('Incomplete development load commands')
        if table is None:
            # Several gated original TUs genuinely produce no code or symbols.
            if expected_type != 1 or any(s['size'] for s in self.sections):
                raise ValueError('Development image lacks a symbol table')
            return
        offset, symbol_count, strings, string_bytes = table
        if offset + 16 * symbol_count > len(self.data) or strings + string_bytes > len(self.data):
            raise ValueError('Truncated development nlist/string table')
        for index in range(symbol_count):
            name, kind, section, descriptor, value = struct.unpack_from('<IBBHQ', self.data, offset + 16 * index)
            if name >= string_bytes or section > len(self.sections):
                raise ValueError('Invalid development symbol ordinal')
            end = self.data.find(b'\0', strings + name, strings + string_bytes)
            if end < 0:
                raise ValueError('Unterminated development symbol')
            spelling = self.data[strings + name:end].decode('ascii')
            if kind & 0xe0:
                continue
            self.symbols.append({'name': spelling, 'kind': kind, 'section': section,
                                 'descriptor': descriptor, 'value': value})

    def named(self, name: str) -> dict:
        matches = [symbol for symbol in self.symbols if symbol['name'] == name and
                   symbol['kind'] & 0x0e == 0x0e and symbol['section']]
        if len(matches) != 1:
            raise ValueError('No unique actual defined symbol: ' + name)
        return matches[0]

    def code(self, name: str) -> dict:
        symbol = self.named(name)
        section = self.sections[symbol['section'] - 1]
        if (section['name'], section['segment']) != ('__text', '__TEXT') or \
                section['flags'] & 0x80000400 != 0x80000400:
            raise ValueError('Actual retained entry is not executable text: ' + name)
        if not section['address'] <= symbol['value'] < section['address'] + section['size']:
            raise ValueError('Actual retained entry lies outside its text section')
        return symbol

    def externals(self) -> dict:
        result = {'strong': [], 'weak': [], 'imports': []}
        for symbol in self.symbols:
            if not symbol['kind'] & 1 or not symbol['name']:
                continue
            if not symbol['name'].startswith('_'):
                raise ValueError('Unexpected Darwin external spelling')
            name = symbol['name'][1:]
            kind = symbol['kind'] & 0x0e
            if kind == 0 and symbol['value'] == 0:
                result['imports'].append(name)
            elif kind == 0:
                raise ValueError('Common symbols cannot substitute a real definition: ' + name)
            elif kind != 0x0e or not symbol['section']:
                raise ValueError('Only actual N_SECT definitions are admitted: ' + name)
            else:
                result['weak' if symbol['descriptor'] & 0x80 else 'strong'].append(name)
        return result


def private_symbol(name: str) -> bool:
    return (name.startswith(('s540', original.PREFIX)) or 'S540' in name or
            name.startswith(('__nvoc_', 'port', 'nv_', 'Rm')))


def audit_symbols(inputs: dict, approved: set[str] | None = None, *,
                  require_private_closure: bool = True,
                  require_reviewed_public: bool = True) -> dict:
    owners, weak, imports = {}, {}, set()
    for name, row in inputs.items():
        for symbol in row['strong']:
            if symbol in owners:
                raise ValueError('Duplicate strong definition: ' + symbol + ' in ' + owners[symbol] + ' and ' + name)
            owners[symbol] = name
        for symbol in row['weak']:
            weak.setdefault(symbol, []).append(name)
        imports.update(row['imports'])
    unresolved = imports - owners.keys() - weak.keys()
    private = sorted(symbol for symbol in unresolved if private_symbol(symbol))
    if private and require_private_closure:
        raise ValueError('Unresolved original/private symbols: ' + repr(private))
    public = unresolved - set(private)
    unknown = sorted(public - approved) if approved is not None else []
    if unknown and require_reviewed_public:
        raise ValueError('Unreviewed public kernel imports: ' + repr(unknown))
    return {'strong_definition_owners': owners, 'weak_definition_owners': weak,
            'unresolved_symbols': sorted(unresolved), 'public_imports': sorted(public),
            'unresolved_original_private': private,
            'unreviewed_public_imports': unknown}


def verify_roots(image: Path, *, expected_type: int) -> dict:
    parsed = Image(image, expected_type)
    table = parsed.named('_s540ProspectiveOriginalRoots')
    section = parsed.sections[table['section'] - 1]
    start = table['value'] - section['address']
    if start < 0 or start + 8 * len(ROOTS) > section['size']:
        raise ValueError('Retained original root table is truncated')
    names = ['_' + original.PREFIX + name for name in ROOTS]
    definitions = [parsed.code(name) for name in names]
    if expected_type == 1:
        obj = metaclass.Object(image)
        target_section = obj.sections[table['section'] - 1]
        relocations = [r for r in obj.relocations(target_section) if start <= r.offset < start + 200]
        if [r.offset for r in relocations] != list(range(start, start + 200, 8)):
            raise ValueError('Every retained root requires an exact pointer relocation')
        for name, relocation in zip(names, relocations):
            if relocation.pc_relative or relocation.kind != 0 or relocation.width != 8:
                raise ValueError('A retained root has an unexpected relocation encoding')
            _, function = obj.target(target_section, relocation)
            if function is None or function.name != name:
                raise ValueError('Retained root does not resolve to its exact original atom: ' + name)
        if not table['descriptor'] & 0x20:
            raise ValueError('The linked root keeper lost N_NO_DEAD_STRIP')
        mechanism = 'all25 exact relocations resolve to defined original text atoms'
    elif expected_type == 11:
        for index, symbol in enumerate(definitions):
            value = struct.unpack_from('<Q', parsed.data, section['offset'] + start + 8 * index)[0]
            if value != symbol['value']:
                raise ValueError('Final retained root slot does not hold exact resolved text address: ' + names[index])
        mechanism = 'all25 final pointer bytes equal their exact defined original text addresses'
    else:
        raise ValueError('Unsupported root proof image type')
    return {'status': 'verified-actual-linked-original-roots', 'root_count': len(names),
        'ordered_roots': names, 'mechanism': mechanism,
        'n_no_dead_strip': bool(table['descriptor'] & 0x20), 'image_sha256': sha(image),
        'actual_original_code_defined': True, 'original_called': False, **GATES}


def loader_pointer_names(image: Path) -> list[tuple[str, str]]:
    obj = metaclass.Object(image)
    entries = []
    for section in obj.sections:
        if section.name not in metaclass.LOADER_TYPES:
            continue
        for relocation in obj.relocations(section):
            _, function = obj.target(section, relocation)
            if function is None:
                raise ValueError('A complete-image loader pointer is not defined code')
            entries.append((section.name, function.name))
    if Counter(name for name, _ in entries) != Counter({'__mod_init_func': 2, '__mod_term_func': 2}):
        raise ValueError('The complete image must retain the exact two initializer/finalizer pairs')
    return entries


def verify_final_loader_pointers(image: Path, expected: list[tuple[str, str]]) -> dict:
    parsed = Image(image, 11)
    # TU finalizer wrappers legitimately share local names such as
    # __GLOBAL__D_a. Preserve their multiplicity; bind final pointers to exact
    # section/address atoms, never to the first symbol with a matching name.
    expected_names = Counter(name for _, name in expected)
    candidates = []
    for name, count in expected_names.items():
        named = [symbol for symbol in parsed.symbols if symbol['name'] == name]
        if len(named) != count:
            raise ValueError('Final loader named-atom multiplicity differs: ' + name)
        for symbol in named:
            if symbol['kind'] & 0x0e != 0x0e or not symbol['section'] or symbol['descriptor'] & 0x0380:
                raise ValueError('Final loader target is weak, alternate, unresolved or non-code')
            section = parsed.sections[symbol['section'] - 1]
            if (section['name'], section['segment']) != ('__text', '__TEXT') or \
                    section['flags'] & 0x80000400 != 0x80000400 or not \
                    section['address'] <= symbol['value'] < section['address'] + section['size']:
                raise ValueError('Final loader atom is outside exact executable text')
            aliases = [other for other in parsed.symbols if
                other['kind'] & 0x0e == 0x0e and other['section'] == symbol['section'] and
                other['value'] == symbol['value']]
            if len(aliases) != 1:
                raise ValueError('Final loader code atom has ambiguous aliases')
            candidates.append(symbol)
    observed, atoms, used = [], [], set()
    for section in parsed.sections:
        kind = section['flags'] & 0xff
        if section['name'] in metaclass.OTHER_LOADER_NAMES or kind == 0x16:
            raise ValueError('Final image contains an unreviewed alternate loader table')
        if section['name'] not in metaclass.LOADER_TYPES:
            if kind in metaclass.LOADER_TYPES.values():
                raise ValueError('Final loader table has an unreviewed section name')
            continue
        if kind != metaclass.LOADER_TYPES[section['name']] or section['size'] % 8:
            raise ValueError('Final loader table type or size differs')
        for offset in range(0, section['size'], 8):
            value = struct.unpack_from('<Q', parsed.data, section['offset'] + offset)[0]
            matches = [symbol for symbol in candidates if symbol['value'] == value and
                       (section['name'], symbol['name']) in expected]
            if len(matches) != 1:
                raise ValueError('Final loader pointer is not the exact previously reviewed entry')
            symbol = matches[0]
            identity = (symbol['section'], symbol['value'])
            if identity in used:
                raise ValueError('Final loader pointers reuse one code atom and omit another')
            used.add(identity)
            observed.append((section['name'], symbol['name']))
            atoms.append({'loader_section': section['name'], 'symbol': symbol['name'],
                          'code_section_ordinal': symbol['section'], 'address': symbol['value']})
    if Counter(observed) != Counter(expected) or len(used) != len(candidates):
        raise ValueError('Final loader entry inventory changed after kext link')
    return {'status': 'verified-final-loader-pointer-targets', 'entries': observed,
            'exact_distinct_code_atoms': atoms, 'duplicate_local_names_preserve_multiplicity': True,
            'reference_graph_audited_on_complete_relocatable_image': True,
            'image_sha256': sha(image), **GATES}


def kernel_flags(sdk: Path) -> tuple[list[str], list[str]]:
    flags = ['-arch', 'x86_64', '-mmacosx-version-min=15.0', '-mkernel',
        '-ffreestanding', '-fno-builtin', '-fno-common', '-fno-stack-protector',
        '-fno-asynchronous-unwind-tables', '-fno-unwind-tables', '-mno-red-zone',
        '-DKERNEL', '-D__KERNEL__', '-O2', '-Wall', '-Wextra', '-Werror',
        '-Wno-deprecated-declarations', '-nostdinc', '-isystem', str(sdk / 'Headers')]
    cpp = execution.kernel_cpp_flags(['-fapple-kext', '-fno-exceptions', '-fno-rtti',
        '-fno-threadsafe-statics', '-nostdinc++', '-std=c++17'])
    return flags, cpp


def verify_closed_loader_policy(composed: Path) -> dict:
    contract_path = LOADER / 'LOADER-PROTOTYPE-CONTRACTS.json'
    if sha(contract_path) != LOADER_CONTRACT_SHA:
        raise ValueError('The reviewed closed loader policy contract changed')
    contract = json.loads(contract_path.read_text())
    if contract.get('entry_policy_closed') is not True or \
            contract.get('original_rm_entry_implemented') is not False:
        raise ValueError('A development image must keep the original-entry policy closed')
    verified = {}
    for name, expected in contract['source_sha256'].items():
        relative = composition.checked_relative(name)
        if relative.suffix not in ('.c', '.cpp', '.h', '.hpp'):
            continue
        path = composed / 'project/packages/nvidia-gsp-bootstrap/prospective-loader' / relative
        if sha(path) != expected:
            raise ValueError('A successor changed the closed loader source: ' + name)
        verified[name] = expected
    return {'contract_sha256': LOADER_CONTRACT_SHA, 'source_sha256': verified,
            'entry_policy_closed': True, 'original_rm_entry_implemented': False}


def project_unit_count(value: dict) -> int:
    profiles = value.get('fixed_source_profiles', {})
    selections=('retained_diagnostic', 'rc_participant', 'shutdown_protocol', 'platform_closure',
                'retained_backends', 'global_epoch', 'live_abi_closure')
    for name in selections:
        if name in profiles and type(profiles[name]) is not bool:
            raise ValueError('A fixed source-profile selection must be a real Boolean')
    expected = (53 + int(profiles.get('rc_participant', False)) +
                int(profiles.get('shutdown_protocol', False)) + int(profiles.get('platform_closure', False)) +
                4*int(profiles.get('live_abi_closure', False)))
    if profiles.get('live_abi_closure') and any(profiles.get(name) is not True for name in selections[:-1]):
        raise ValueError('The live ABI source profile requires all retained transaction dependencies')
    if len(value['project_translation_units']) != expected:
        raise ValueError('The source composition lost a baseline or selected successor translation unit')
    for name in ('original_entry_admission', 'hardware_admission', 'final_release_issued', 'stop_receipt_issued'):
        if name in profiles and profiles[name] is not False:
            raise ValueError('A fixed source profile tried to issue runtime admission or a stop/release receipt')
    return expected


def require_fresh_native_composition(plan_only: bool, composition_dir: Path | None) -> None:
    if not plan_only and composition_dir is not None:
        raise ValueError('Native image builds require a fresh canonical composition and compile; '
                         '--composition-dir is accepted only with --plan-only')


def verify_source_definitions(command: list[str], expected: dict, scoped: set[str]) -> None:
    observed={name:[] for name in scoped}
    index=0
    while index<len(command):
        flag=command[index];index+=1
        if flag in ('-D','-U'):
            if index==len(command):raise ValueError('Incomplete source-profile definition option')
            flag+=command[index];index+=1
        if flag.startswith('-D'):
            name,_,value=flag[2:].partition('=')
            if name in scoped:observed[name].append(value or '1')
        elif flag.startswith('-U') and flag[2:] in scoped:
            raise ValueError('A fixed source-profile definition was explicitly undefined')
    if any(values != ([expected[name]] if name in expected else []) for name,values in observed.items()):
        raise ValueError('Fixed source-profile definitions escaped or differ from their exact source')


def verify_closed_character_frontend(image: Image, value: dict) -> dict:
    profiles=value.get('fixed_source_profiles',{})
    if not profiles.get('live_abi_closure'):
        return {'selected':False,'character_frontend_exclusion_proven':False}
    ingress=profiles.get('live_abi_source_profile',{}).get('control_event_ingress',{})
    if ingress.get('sole_control_event_insertion_function')!='allocate_os_event' or \
            ingress.get('original_user_dispatcher')!='rm_ioctl' or \
            ingress.get('private_user_dispatcher_exposed_by_loader') is not False:
        raise ValueError('The live control-state source profile lost its exact event insertion route')
    forbidden={'_'+original.PREFIX+'rm_ioctl','_rm_ioctl',
               '_'+original.PREFIX+'allocate_os_event','_allocate_os_event'}
    retained=sorted(symbol['name'] for symbol in image.symbols if
        any(symbol['name']==name or symbol['name'].startswith((name+'.',name+'$')) for name in forbidden)
        and symbol['kind']&0x0e==0x0e and symbol['section'])
    if retained:raise ValueError('A character-device/event insertion frontend survived final dead stripping: '+repr(retained))
    return {'selected':True,'character_frontend_exclusion_proven':True,
        'forbidden_defined_symbols':sorted(forbidden),'retained_forbidden_symbols':[],
        'source_ingress':ingress,'closed_loader_source_verified_separately':True,
        'os_event_delivery_implemented':False}


def compilation_inputs(directory: Path, report: dict, *, original_units: bool,
                       expected_project_units: int = 53,
                       planned_original_sources: list[str] | None = None) -> list[Path]:
    expected = 'compiled-full-original-source-only' if original_units else 'compiled-project-source-only'
    native = report.get('native_darwin_compilation', report.get('authoritative_darwin_execution'))
    if report.get('status') != expected or native is not True or \
            report.get('host_control') is not False:
        raise ValueError('Only complete native Apple compilation may enter the final link')
    if report.get('composition_sha256') != sha(directory / 'composition.json'):
        raise ValueError('Native objects belong to a different exact source composition')
    rows = report['results']
    if len(rows) != (1100 if original_units else expected_project_units):
        raise ValueError('Final link lost an exact original/project translation unit')
    folder = directory / ('original-objects' if original_units else 'project-objects')
    manifest=composition.verify_composition(directory)
    per_original=manifest.get('fixed_source_profiles',{}).get('per_original_source_compile_definitions',{})
    scoped={name for definitions in per_original.values() for name in definitions}
    scoped.update(name for item in manifest['project_translation_units']
                  for name in item.get('compile_definitions',{}) if name.startswith('S540_NVIDIA_'))
    if original_units:
        if planned_original_sources is None or len(set(planned_original_sources)) != 1100:
            raise ValueError('Original native reuse requires the actual exact 1100-source make plan')
        expected_sources = set(planned_original_sources)
        source_rows = {}
    else:
        source_rows = {row['source']: row for row in manifest['project_translation_units']}
        if len(source_rows) != expected_project_units:
            raise ValueError('The canonical project source inventory is incomplete')
        expected_sources = set(source_rows)
    observed_sources = [row['source'] for row in rows]
    if len(set(observed_sources)) != len(observed_sources) or set(observed_sources) != expected_sources:
        raise ValueError('Compiler rows do not match the exact one-to-one composed source inventory')
    for row in rows:
        relative = composition.checked_relative(row['source'])
        if original_units:
            source = (folder / 'g_nvid_string.c' if row['source'] == 'generated/g_nvid_string.c'
                      else directory / 'source' / relative)
            expected_source_hash = row['source_sha256']
            expected_cwd = directory / 'source/src/nvidia'
            expected_definitions=per_original.get(row['source'],{})
            if row.get('compile_definitions',{})!=expected_definitions:
                raise ValueError('Original compiler per-source definitions differ from exact source profile')
        else:
            declared = source_rows[row['source']]
            if row['kind'] != declared['kind'] or row['sha256'] != declared['sha256']:
                raise ValueError('Compiler source kind/hash differs from its exact declared source')
            if row.get('compile_definitions', {}) != declared.get('compile_definitions', {}):
                raise ValueError('Compiler per-source definitions differ from the composed source row')
            source, expected_source_hash = directory / 'project' / relative, declared['sha256']
            expected_cwd = directory / 'project'
            expected_definitions=declared.get('compile_definitions',{})
        verify_source_definitions(row['command'],expected_definitions,scoped)
        if sha(source) != expected_source_hash:
            raise ValueError('Native compiler source bytes changed: ' + row['source'])
        cwd = Path(row['cwd']).resolve(strict=True)
        if cwd != expected_cwd.resolve(strict=True):
            raise ValueError('Native compiler source was built outside its exact composed tree')
        command_source = Path(row['command'][row['command'].index('-c') + 1])
        command_source = command_source if command_source.is_absolute() else cwd / command_source
        if command_source.resolve(strict=True) != source.resolve(strict=True):
            raise ValueError('Native compiler command did not compile its claimed source row')
        platform_flags = [flag for flag in row['command'] if
                          flag.startswith('-DS540_NVIDIA_DARWIN_PLATFORM_CLOSURE')]
        if row['source'] == PLATFORM_SOURCE:
            if row.get('compile_definitions') != PLATFORM_DEFINITIONS or \
                    any(row['command'].count('-D' + name + '=' + value) != 1
                        for name, value in PLATFORM_DEFINITIONS.items()) or \
                    any(flag.startswith('-DNV_PM_RUNTIME_AVAILABLE') for flag in row['command']):
                raise ValueError('Platform identity/utility closure requires its exact non-PM per-source definitions')
        elif platform_flags:
            raise ValueError('Platform closure macro escaped its one declared source')
    composition.verify_compiled_rows(rows, folder)
    objects = []
    for row in rows:
        name = Path(row['object'])
        if name.name != str(name):
            raise ValueError('A compiled object name escapes its declared directory')
        obj = folder / name
        if obj.is_symlink() or sha(obj) != row['object_sha256']:
            raise ValueError('Final link input object changed: ' + str(obj))
        for name, expected_hash in row['dependency_sha256'].items():
            if sha(Path(name)) != expected_hash:
                raise ValueError('Final link compiler dependency changed: ' + name)
        objects.append(obj)
    if len(objects) != len(set(objects)):
        raise ValueError('Final link contains a duplicate object path')
    return objects


def sdk_import_references(output: Path, composed: Path, cxx: Path,
                          flags: list[str], cpp: list[str], project_rows: list[dict],
                          execute) -> tuple[set[str], dict, Path, Path]:
    references = [
        'packages/nvidia-darwin-services/tests/sdk_import_reference.cpp',
        'packages/nvidia-global-rm/tests/sdk_import_reference.cpp',
        'packages/nvidia-device-transport/tests/sdk_import_reference.cpp',
        'packages/nvidia-gsp-bootstrap/platform/tests/sdk_import_reference.cpp',
        'packages/nvidia-gsp-bootstrap/platform/tests/sdk_power_reference.cpp',
        'packages/nvidia-gsp-bootstrap/tests/sdk_dispatcher_reference.cpp']
    approved = {name[1:] for name in transport.ADAPTER_IMPORTS}
    rows = {}
    include = composition.include_flags(composed)
    declared_sources = [(relative, ROOT / relative) for relative in references]
    for label, text in [('hardware-transport', transport.HARDWARE_IMPORT_REFERENCE),
                        ('rm-services', transport.SERVICES_IMPORT_REFERENCE),
                        ('closed-loader-operations', LOADER_OPERATION_REFERENCE)]:
        source = output / ('sdk-declared-' + label + '.cpp')
        source.write_text(text)
        owner = Path(__file__).name if label == 'closed-loader-operations' else 'build_nvidia_transport.py'
        declared_sources.append((owner + ':' + label + '-authored-reference', source))
    for index, (relative, source) in enumerate(declared_sources):
        obj = output / ('sdk-operation-reference-%02d.o' % index)
        execute([cxx, *flags, *cpp, *include, '-c', source, '-o', obj], 'sdk-reference-%02d' % index)
        defined, imports, _ = original.macho_symbols(obj)
        metaclass.verify_no_initializers(obj)
        approved.update(imports)
        rows[relative] = {'source_sha256': sha(source), 'object_sha256': sha(obj),
                          'imports': sorted(imports), 'definitions': sorted(defined)}
    power_ref = metaclass.compile_reference(output, [*flags, *include], cpp, compiler=[str(cxx)])
    loader_ref = output / 'sdk-loader-metaclass-reference.o'
    loader_source = LOADER / 'tests/sdk_loader_metaclass_reference.cpp'
    execute([cxx, *flags, *cpp, *include, '-c', loader_source, '-o', loader_ref], 'loader-reference')
    lookup = {row['source']: composed / 'project-objects' / row['object'] for row in project_rows}
    power = lookup['packages/nvidia-gsp-bootstrap/platform/S540NvidiaGspPower.cpp']
    loader = lookup['packages/nvidia-gsp-bootstrap/prospective-loader/S540ProspectiveLoaderKernel.cpp']
    inherited, dependencies = metaclass.framework_imports(power, power_ref)
    approved.update(name[1:] for name in inherited)
    loader_check = load('s540_link_loader_check', LOADER / 'check_loader.py')
    loader_check.loader_graph(loader, loader_ref)
    actual_definitions, _, _ = original.macho_symbols(loader, reviewed_project_initializers=True)
    _, loader_imports, _ = original.macho_symbols(loader_ref, reviewed_project_initializers=True)
    private_prefixes = tuple(prefix + str(len(name)) + name for prefix in ('_ZN', '_ZNK')
        for name in ('S540ProspectiveLoaderControl', 'S540ProspectiveLoaderClient'))
    private = {name for name in loader_imports if name.startswith(private_prefixes)}
    if private - actual_definitions:
        raise ValueError('Loader reference requires unimplemented project overrides: ' + repr(sorted(private - actual_definitions)))
    ancestors = ('OSMetaClass', 'OSMetaClassBase', 'OSObject', 'IORegistryEntry', 'IOService', 'IOUserClient')
    framework_prefixes = tuple(prefix + str(len(name)) + name for prefix in ('_ZN', '_ZNK') for name in ancestors)
    framework = loader_imports - private
    if any(not name.startswith(framework_prefixes) for name in framework):
        raise ValueError('Loader SDK reference imported outside its reviewed ancestry')
    approved.update(framework)
    rows['power-metaclass-framework'] = {'imports': sorted(name[1:] for name in inherited),
        'private_project_dependencies': sorted(dependencies), 'object_sha256': sha(power_ref),
        'source_sha256': sha(metaclass.REFERENCE), 'class_declaration_sha256': sha(metaclass.CLASS_HEADER)}
    rows['loader-metaclass-framework'] = {'imports': sorted(framework),
        'private_project_dependencies': sorted(private), 'object_sha256': sha(loader_ref),
        'source_sha256': sha(loader_source)}
    return approved, rows, power_ref, loader_ref


def build(args) -> dict:
    inputs = [args.upstream, args.v3_root, args.namespace, args.kernel_sdk,
              args.assets_dir, ROOT / 'packages']
    if args.composition_dir is not None:
        inputs.append(args.composition_dir)
    for manifest in [args.successor_manifest, args.project_successor_manifest]:
        if manifest is not None:
            inputs.append(manifest.parent)
    output = composition.new_output(args.output, inputs)
    output.mkdir(parents=True)
    report = {'format': 1, 'status': 'running', 'phase': 'validate-inputs',
              'actual_link_performed': False, 'final_link_attempted': False, **GATES}
    builders = [Path(__file__).resolve(), ROOT / 'builders/compose_nvidia_first_transaction.py',
        ROOT / 'builders/build_nvidia_execution.py', ROOT / 'builders/build_nvidia_transport.py',
        ROOT / 'builders/compile_nvidia_global_rm.py', ROOT / 'builders/nvidia_combined_metaclasses.py',
        ROOT / 'builders/nvidia_metaclass_initializers.py', ROOT / 'builders/embed_nvidia_firmware.py']
    builder_hashes = {str(path): sha(path) for path in builders}
    report['builder_source_sha256'] = builder_hashes
    destination = output / 'first-transaction-image.json'
    write_json(destination, report)
    commands = []
    report['commands'] = commands
    def execute(command, name, *, cwd=None, timeout=300):
        command = [str(value) for value in command]
        result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        (output / (name + '.log')).write_text(result.stdout + result.stderr)
        commands.append({'name': name, 'command': command, 'cwd': str(cwd) if cwd else None,
                         'status': result.returncode})
        if result.returncode:
            report['failure_diagnostics'] = {'step': name, 'log': name + '.log',
                                             'stderr_tail': result.stderr[-12000:]}
            raise RuntimeError('Native development step failed: ' + name + '; see ' + str(output / (name + '.log')))
        return result
    try:
        require_fresh_native_composition(args.plan_only, args.composition_dir)
        common = load('s540_first_image_common', GSP / 'prospective-first-transaction/original/common.py')
        cc, cxx = common.compiler(str(args.cc)), common.compiler(str(args.cxx))
        native = sys.platform == 'darwin' and platform.machine() == 'x86_64'
        if not args.plan_only and not native:
            raise ValueError('Actual combined-image linking requires Intel macOS; --plan-only performs no compile/link')
        identity = common.execution_identity(cc, cxx, not native)
        identity['native_darwin_compilation'] = identity.pop('authoritative_darwin_execution')
        report.update(identity)
        if args.sdk_archive is not None and not args.plan_only:
            raise ValueError('Native final image validation requires the clean pinned SDK Git checkout')
        sdk = args.kernel_sdk.resolve(strict=True)
        sdk_record = common.validate_sdk(sdk, args.sdk_archive, not native)
        assets = args.assets_dir.resolve(strict=True)
        firmware_assets = firmware.ACQUIRE.verify_assets(assets)
        report.update(sdk=sdk_record, firmware_asset_inventory=firmware_assets)
        if args.composition_dir is None:
            composed = output / 'composition'
            value = composition.materialize(args.upstream, args.v3_root, args.namespace, composed,
                successor_manifest=args.successor_manifest,
                project_successor_manifest=args.project_successor_manifest,
                retained_diagnostic=args.retained_diagnostic, rc_participant=args.rc_participant,
                shutdown_protocol=args.shutdown_protocol, platform_closure=args.platform_closure,
                retained_backends=args.retained_backends, global_epoch=args.global_epoch,
                live_abi_closure=args.live_abi_closure)
        else:
            composed = args.composition_dir.resolve(strict=True)
            value = composition.verify_composition(composed)
            if args.successor_manifest or args.project_successor_manifest:
                raise ValueError('Successor manifests cannot alter a reused composition')
            for name in ('retained_diagnostic', 'rc_participant', 'shutdown_protocol', 'platform_closure',
                         'retained_backends', 'global_epoch', 'live_abi_closure'):
                if getattr(args, name) and value.get('fixed_source_profiles', {}).get(name) is not True:
                    raise ValueError('Requested fixed source profile is absent from reused composition: ' + name)
        report.update(composition_directory=str(composed), composition_sha256=sha(composed / 'composition.json'))
        report['closed_loader_policy'] = verify_closed_loader_policy(composed)
        project_units = project_unit_count(value)
        if value['original_file_count'] != 4005:
            raise ValueError('The final image requires the exact 4005-file original source composition')
        report['fixed_source_profiles'] = value.get('fixed_source_profiles', {})
        if any(value.get(name) is not False for name in
               ('original_entry_admission', 'production_candidate_allowed', 'hardware_admission')):
            raise ValueError('A source composition attempted to enable runtime admission')
        flags, cpp = kernel_flags(sdk)
        planned_sources = [row['source'] for row in value['project_translation_units']]
        declared_original = original.original_commands(args.upstream.resolve(strict=True),
                                                       output / 'original-command-plan', cc)
        original_source_root = composed / 'source/src/nvidia'
        original_sources = []
        original_targets = []
        for command in declared_original:
            source = Path(command[command.index('-c') + 1])
            target = Path(command[command.index('-o') + 1]).name
            original_targets.append(target)
            if source.is_absolute():
                if source.name != 'g_nvid_string.c':
                    raise ValueError('An undeclared generated original source entered the link plan')
                original_sources.append('generated/g_nvid_string.c')
            else:
                actual = (original_source_root / source).resolve(strict=True)
                relative = actual.relative_to(composed / 'source').as_posix()
                if sha(actual) != value['original_files'][relative]['sha256']:
                    raise ValueError('A planned original source differs from exact composition')
                original_sources.append(relative)
        if len(set(original_sources)) != 1100 or len(set(original_targets)) != 1100:
            raise ValueError('The declared upstream link plan duplicates a source or target')
        report['source_plan'] = {'complete_original_translation_units': 1100,
            'canonical_project_translation_units': project_units, 'project_sources': planned_sources,
            'declared_original_sources': original_sources,
            'make_declared_original_source_plan_verified': True,
            'firmware_objects': 1, 'pinned_libkmod_c_wrappers': ['c_start.o', 'c_stop.o'],
            'total_expected_link_objects': 1100 + project_units + 3, 'native_sdk_kernel_flags': flags,
            'native_cpp_flags': cpp, 'link_strategy': 'same complete ld-r image then raw development MH_KEXT_BUNDLE',
            'dead_strip': 'final-kext-only; complete ld-r retains every input atom',
            'installable_kext_path': None,
            'complete_metaclass_classes': ['S540NvidiaGspPowerService', 'S540ProspectiveLoaderControl',
                                            'S540ProspectiveLoaderClient'],
            'retained_original_roots': list(ROOTS)}
        if args.plan_only:
            composition.verify_composition(composed)
            if any(sha(Path(path)) != digest for path, digest in builder_hashes.items()):
                raise ValueError('A development build helper changed during source-plan validation')
            report.update(status='validated-source-plan-only', phase='done',
                          actual_link_performed=False, original_compilation_performed=False,
                          project_compilation_performed=False, final_image=None)
            return report
        report['phase'] = 'compile-complete-source-composition'
        write_json(destination, report)
        original_report_path = composed / 'full-original-compilation.json'
        project_report_path = composed / 'project-compilation.json'
        if original_report_path.exists() or project_report_path.exists():
            raise ValueError('Fresh native image builds must not reuse any preexisting compilation report')
        originals = composition.compile_original_objects(args.upstream, composed, cc, host_control=False)
        projects = composition.compile_project_objects(args.upstream, composed, cc, cxx, flags, cpp, host_control=False)
        report['original_compilation_performed'] = True
        report['project_compilation_performed'] = True
        original_objects = compilation_inputs(composed, originals, original_units=True,
                                               planned_original_sources=original_sources)
        project_objects = compilation_inputs(composed, projects, original_units=False,
                                              expected_project_units=project_units)
        report['compilation_reports'] = {'original_sha256': sha(original_report_path),
            'project_sha256': sha(project_report_path), 'original_objects': len(original_objects),
            'project_objects': len(project_objects)}
        report['phase'] = 'compile-independent-sdk-references'
        write_json(destination, report)
        approved, reference_report, power_ref, loader_ref = sdk_import_references(
            output, composed, cxx, flags, cpp, projects['results'], execute)
        report['independent_sdk_references'] = reference_report
        report['approved_public_imports'] = sorted(approved)
        report['phase'] = 'embed-exact-firmware-and-module-wrappers'
        write_json(destination, report)
        assembly, embedding = firmware.emit_assembly(assets, output)
        firmware_object = output / 'firmware-bytes.o'
        execute([cc, '-arch', 'x86_64', '-mmacosx-version-min=15.0', '-c', assembly,
                 '-o', firmware_object], 'firmware-assemble', cwd=assets)
        report['firmware_embedding'] = embedding
        report['firmware_object'] = firmware.verify_embedded_firmware(firmware_object)
        archive = sdk / 'Library/x86_64/libkmod.a'
        wrapper_objects, wrapper_reports = [], []
        for member, permitted in [('c_start.o', {'_realmain', 'kmod_info'}), ('c_stop.o', {'_antimain'})]:
            raw = subprocess.run(['/usr/bin/ar', 'p', str(archive), member], capture_output=True, check=True).stdout
            target = output / member
            target.write_bytes(raw)
            defined, imported, _ = original.macho_symbols(target)
            metaclass.verify_no_initializers(target)
            if imported != permitted:
                raise ValueError('The pinned SDK module C wrapper acquired unexpected imports')
            wrapper_objects.append(target)
            wrapper_reports.append({'member': member, 'sha256': sha(target),
                                    'imports': sorted(imported), 'definitions': sorted(defined)})
        report['pinned_module_runtime'] = {'archive_sha256': sha(archive), 'members': wrapper_reports,
                                           'legacy_libkmod_cpp_used': False}
        objects = [*original_objects, *project_objects, firmware_object, *wrapper_objects]
        if len(objects) != 1100 + project_units + 3 or len(objects) != len(set(objects)):
            raise ValueError('The complete native link input inventory changed')
        before = {str(path): sha(path) for path in objects}
        input_symbols = {str(path): Image(path, 1).externals() for path in objects}
        input_audit = audit_symbols(input_symbols, require_private_closure=False)
        report['input_symbol_audit'] = input_audit
        report['input_object_sha256'] = before
        report['phase'] = 'link-same-complete-relocatable-image'
        write_json(destination, report)
        apple_ld = Path(execute(['/usr/bin/xcrun', '--find', 'ld'], 'find-apple-linker').stdout.strip()).resolve(strict=True)
        ld = args.ld.resolve(strict=True) if args.ld else apple_ld
        if ld != apple_ld:
            raise ValueError('The final development image requires the actual selected Apple linker')
        report['apple_linker'] = {'path': str(ld), 'sha256': sha(ld)}
        image = output / 'S540FirstTransactionDevelopment.o'
        execute([ld, '-r', '-arch', 'x86_64', *objects, '-o', image], 'complete-relocatable-link', timeout=900)
        linked_symbols = Image(image, 1).externals()
        linked_audit = audit_symbols({image.name: linked_symbols}, approved,
            require_private_closure=False, require_reviewed_public=False)
        if linked_audit['unresolved_symbols'] != input_audit['unresolved_symbols']:
            raise ValueError('Actual complete linker imports differ from exact input symbol closure')
        all_input_definitions = set(input_audit['strong_definition_owners']) | set(input_audit['weak_definition_owners'])
        if set(linked_symbols['strong']) | set(linked_symbols['weak']) != all_input_definitions:
            raise ValueError('The non-dead-stripping combined image lost or gained an external definition')
        report['relocatable_image'] = {'path': image.name, 'sha256': sha(image),
            'bytes': image.stat().st_size, 'imports': linked_audit['public_imports'],
            'unresolved_original_private': linked_audit['unresolved_original_private'],
            'unreviewed_public_imports': linked_audit['unreviewed_public_imports'],
            'defined_external_count': len(all_input_definitions)}
        report['actual_link_performed'] = True
        report['relocatable_link_performed'] = True
        report['combined_metaclasses'] = combined_metaclasses.verify(image, power_ref, loader_ref)
        report['relocatable_original_roots'] = verify_roots(image, expected_type=1)
        report['relocatable_embedded_firmware'] = firmware.verify_embedded_firmware(image)
        loader_entries = loader_pointer_names(image)
        report['relocatable_import_scope'] = ('all compiled inputs; dormant input imports do not '
            'establish selected final-image requirements. Native final dead-strip link determines live closure.')
        report['phase'] = 'link-raw-development-kext-image'
        write_json(destination, report)
        hidden = output / 'private-original-symbols.txt'
        hidden.write_text(''.join('_' + symbol + '\n' for symbol in sorted(all_input_definitions)
                                  if symbol.startswith(original.PREFIX)))
        final = output / 'S540FirstTransactionDevelopment.macho'
        retained = ['__start', '__stop', '_kmod_info', '_s540ProspectiveRetainedRootsPresent',
                    '_s540_gsp_begin', '_s540_gsp_end', '_s540_ucodes_begin', '_s540_ucodes_end']
        report['final_link_policy'] = {'dead_strip': True, 'undefined_policy': 'error',
            'allowed_undefined_public_symbols': sorted('_' + name for name in approved),
            'additional_retained_root_symbols': retained,
            'typed25_root_table_retention': 'actual N_NO_DEAD_STRIP and final pointer-byte verification',
            'original_definition_visibility': 'hidden; not implicitly exported roots',
            'unresolved_private_imports_permitted': False}
        report['final_link_attempted'] = True
        write_json(destination, report)
        execute([cxx, '-fuse-ld=' + str(ld), '-arch', 'x86_64', '-mmacosx-version-min=15.0', '-mkernel', '-nostdlib',
            '-Wl,-kext', '-Wl,-no_source_version', '-Wl,-dead_strip', '-Wl,-undefined,error',
            '-Wl,-unexported_symbols_list,' + str(hidden),
            *[flag for name in sorted(approved) for flag in ['-Xlinker', '-U', '-Xlinker', '_' + name]],
            *[flag for name in retained for flag in ['-Xlinker', '-u', '-Xlinker', name]],
            image, '-o', final], 'raw-development-kext-link', timeout=900)
        final_image = Image(final, 11)
        final_symbols = final_image.externals()
        final_audit = audit_symbols({final.name: final_symbols}, approved)
        if set(final_audit['public_imports']) - set(linked_audit['public_imports']):
            raise ValueError('Final kernel image gained an import absent from the complete ld-r image')
        for symbol in ('__start', '__stop'):
            final_image.code(symbol)
        for symbol in ('_kmod_info', '__realmain', '__antimain'):
            final_image.named(symbol)
        report['final_original_roots'] = verify_roots(final, expected_type=11)
        report['final_loader_pointers'] = verify_final_loader_pointers(final, loader_entries)
        report['final_embedded_firmware'] = firmware.verify_embedded_firmware(final)
        report['final_character_frontend'] = verify_closed_character_frontend(final_image,value)
        composition.verify_composition(composed)
        verify_closed_loader_policy(composed)
        compilation_inputs(composed, originals, original_units=True,
                           planned_original_sources=original_sources)
        compilation_inputs(composed, projects, original_units=False,
                           expected_project_units=project_units)
        if any(sha(Path(path)) != digest for path, digest in before.items()):
            raise ValueError('An actual image input changed during final linking')
        common.validate_sdk(sdk, None, False)
        firmware.ACQUIRE.verify_assets(assets)
        if sha(ld) != report['apple_linker']['sha256'] or \
                any(sha(Path(path)) != digest for path, digest in builder_hashes.items()):
            raise ValueError('A development linker/helper input changed during compilation/linking')
        report.update(status='linked-native-development-image', phase='done', actual_link_performed=True,
            native_compilation_reports_verified=True,
            final_image={'path': final.name, 'sha256': sha(final), 'bytes': final.stat().st_size,
                         'filetype': 'MH_KEXT_BUNDLE', 'imports': final_audit['public_imports'],
                         'installable_bundle': False}, target_kernel_admission_proven=False,
            aggregate_stack_proven=False, hardware_stop_proven=False)
        return report
    except Exception as error:
        report.update(status='failed', failure_type=type(error).__name__, failure=str(error))
        raise
    finally:
        write_json(destination, report)


def self_test() -> dict:
    """Exercise the linker-admission logic independently of a native linker."""
    checks = 0
    def rejected(rows, approved, phrase):
        nonlocal checks
        try:
            audit_symbols(rows, approved)
        except ValueError as error:
            if phrase not in str(error):
                raise
            checks += 1
        else:
            raise AssertionError('An invalid link plan was accepted: ' + phrase)
    empty = lambda **fields: {'strong': [], 'weak': [], 'imports': [], **fields}
    rows = {'original': empty(strong=['s540Global_real']),
            'bridge': empty(strong=['s540Bridge'], imports=['s540Global_real', 'IOMalloc'])}
    result = audit_symbols(rows, {'IOMalloc'})
    assert result['public_imports'] == ['IOMalloc'] and not result['unresolved_original_private']
    checks += 1
    unresolved = audit_symbols({'bridge': empty(imports=['s540Global_missing', 'IOMalloc'])},
        {'IOMalloc'}, require_private_closure=False)
    assert unresolved['unresolved_original_private'] == ['s540Global_missing'] and \
        unresolved['public_imports'] == ['IOMalloc']
    checks += 1
    rejected({**rows, 'duplicate': empty(strong=['s540Global_real'])}, {'IOMalloc'}, 'Duplicate strong')
    rejected({'bridge': empty(imports=['s540Global_missing'])}, {'s540Global_missing'}, 'Unresolved original/private')
    rejected({'bridge': empty(imports=['_ZN28S540ProspectiveLoaderControl4freeEv'])}, set(), 'Unresolved original/private')
    rejected({'bridge': empty(imports=['UnauthoredKernelOperation'])}, {'IOMalloc'}, 'Unreviewed public')
    weak = audit_symbols({'one': empty(weak=['coalesced']), 'two': empty(weak=['coalesced'], imports=['coalesced'])}, set())
    assert not weak['public_imports'] and len(weak['weak_definition_owners']['coalesced']) == 2
    checks += 1
    assert len(ROOTS) == len(set(ROOTS)) == 25 and not any(GATES[name] for name in
        ('original_entry_admission', 'production_candidate_allowed', 'hardware_admission', 'module_loaded'))
    checks += 1
    require_fresh_native_composition(True, Path('source-plan-inspection-only'))
    try:
        require_fresh_native_composition(False, Path('previous-compilation'))
    except ValueError as error:
        assert '--composition-dir is accepted only with --plan-only' in str(error)
        checks += 1
    else:
        raise AssertionError('A native build accepted unbound reused compiler commands/SDK inputs')
    selected = {'project_translation_units': [{}] * 55,
        'fixed_source_profiles': {'retained_diagnostic': True, 'rc_participant': True,
                                 'shutdown_protocol': True, 'stop_receipt_issued': False}}
    assert project_unit_count(selected) == 55
    checks += 1
    closed={'project_translation_units':[{}]*60,'fixed_source_profiles':{name:True for name in
        ('retained_diagnostic','rc_participant','shutdown_protocol','platform_closure',
         'retained_backends','global_epoch','live_abi_closure')}}
    assert project_unit_count(closed)==60
    checks += 1
    scoped={'S540_NVIDIA_NO_OS_EVENT_BACKEND','S540_NVIDIA_NO_CHARACTER_DEVICE'}
    verify_source_definitions(['clang','-D','S540_NVIDIA_NO_OS_EVENT_BACKEND=1'],
                              {'S540_NVIDIA_NO_OS_EVENT_BACKEND':'1'},scoped)
    verify_source_definitions(['clang'],{},scoped)
    checks += 2
    for command,expected in [
        (['-DS540_NVIDIA_NO_OS_EVENT_BACKEND=1'],{}),
        ([],{'S540_NVIDIA_NO_OS_EVENT_BACKEND':'1'}),
        (['-DS540_NVIDIA_NO_OS_EVENT_BACKEND=0'],{'S540_NVIDIA_NO_OS_EVENT_BACKEND':'1'}),
        (['-DS540_NVIDIA_NO_OS_EVENT_BACKEND=1']*2,{'S540_NVIDIA_NO_OS_EVENT_BACKEND':'1'}),
        (['-D','S540_NVIDIA_NO_OS_EVENT_BACKEND=1','-U','S540_NVIDIA_NO_OS_EVENT_BACKEND'],
             {'S540_NVIDIA_NO_OS_EVENT_BACKEND':'1'})]:
        try:verify_source_definitions(command,expected,scoped)
        except ValueError:checks+=1
        else:raise AssertionError('Escaped or modified source-profile definitions were accepted')
    class FrontendFixture:
        symbols=[]
    frontend_profile={'fixed_source_profiles':{'live_abi_closure':True,'live_abi_source_profile':
        {'control_event_ingress':{'sole_control_event_insertion_function':'allocate_os_event',
          'original_user_dispatcher':'rm_ioctl','private_user_dispatcher_exposed_by_loader':False}}}}
    assert verify_closed_character_frontend(FrontendFixture(),frontend_profile)['character_frontend_exclusion_proven']
    checks+=1
    for name in ('_s540Global_rm_ioctl','_allocate_os_event','_allocate_os_event.cold.1'):
        fixture=FrontendFixture();fixture.symbols=[{'name':name,'kind':0x0e,'section':1}]
        try:verify_closed_character_frontend(fixture,frontend_profile)
        except ValueError:checks+=1
        else:raise AssertionError('A live character/event insertion frontend was admitted')
    for invalid, phrase in [
        ({**selected, 'project_translation_units': [{}] * 54}, 'selected successor translation unit'),
        ({**selected, 'fixed_source_profiles': {**selected['fixed_source_profiles'],
                                               'stop_receipt_issued': True}}, 'stop/release receipt'),
        ({**closed,'fixed_source_profiles':{**closed['fixed_source_profiles'],'global_epoch':False}},
             'retained transaction dependencies'),
        ({**closed,'fixed_source_profiles':{**closed['fixed_source_profiles'],'live_abi_closure':1}},
             'real Boolean')]:
        try:
            project_unit_count(invalid)
        except ValueError as error:
            assert phrase in str(error)
            checks += 1
        else:
            raise AssertionError('An invalid selected source profile was accepted')
    # Deliberately synthetic Mach-O containers exercise actual pointer/ordinal
    # parsing. Their bytes are never passed off as compiled NVIDIA code.
    def root_fixture(kind, *, bad_pointer=False, missing_relocation=False, data_root=False):
        text_bytes, data_bytes = 16 * len(ROOTS), 8 * len(ROOTS)
        commands = 72 + 2 * 80 + 24
        text_offset, data_offset = 32 + commands, 32 + commands + text_bytes
        relocation_offset = data_offset + data_bytes
        relocation_count = len(ROOTS) - (1 if missing_relocation else 0) if kind == 1 else 0
        symbols_offset = relocation_offset + 8 * relocation_count
        names = ['_' + original.PREFIX + name for name in ROOTS] + ['_s540ProspectiveOriginalRoots']
        strings, offsets = b'\0', []
        for name in names:
            offsets.append(len(strings))
            strings += name.encode() + b'\0'
        string_offset = symbols_offset + 16 * len(names)
        result = bytearray(struct.pack('<8I', 0xfeedfacf, 0x01000007, 3, kind, 2, commands, 0, 0))
        result.extend(struct.pack('<II16sQQQQIIII', 0x19, 72 + 160, b'', 0, 0, 0, 0, 7, 7, 2, 0))
        for section, segment, address, size, offset, rel_offset, rel_count, flags in [
            (b'__text', b'__TEXT', 0x1000, text_bytes, text_offset, 0, 0, 0x80000400),
            (b'__const', b'__DATA', 0x2000, data_bytes, data_offset,
             relocation_offset if relocation_count else 0, relocation_count, 0)]:
            result.extend(struct.pack('<16s16sQQIIIIIIII', section, segment, address, size,
                offset, 3, rel_offset, rel_count, flags, 0, 0, 0))
        result.extend(struct.pack('<6I', 2, 24, symbols_offset, len(names), string_offset, len(strings)))
        result.extend((b'\xc3' + b'\x90' * 15) * len(ROOTS))
        for index in range(len(ROOTS)):
            value = 0 if kind == 1 else 0x1000 + 16 * index
            if bad_pointer and index == 4:
                value += 1
            result.extend(struct.pack('<Q', value))
        for index in range(relocation_count):
            result.extend(struct.pack('<II', 8 * index, index | (3 << 25) | (1 << 27)))
        for index, offset in enumerate(offsets):
            table = index == len(ROOTS)
            result.extend(struct.pack('<IBBHQ', offset, 0x0e if table else 0x0f,
                2 if table or data_root and index == 2 else 1,
                0x20 if table else 0, 0x2000 if table else 0x1000 + 16 * index))
        result.extend(strings)
        return result
    loader_expected = [('__mod_init_func', '__GLOBAL__sub_I_power'),
                       ('__mod_init_func', '__GLOBAL__sub_I_loader'),
                       ('__mod_term_func', '__GLOBAL__D_a'),
                       ('__mod_term_func', '__GLOBAL__D_a')]
    def loader_fixture(*, reverse_terms=False, duplicate_pointer=False, extra_atom=False,
                       alias=False, interior=False, weak=False, alternate=False):
        definitions = [(name, 0x1000 + 16 * index, 0) for index, (_, name) in enumerate(loader_expected)]
        if weak or alternate:
            name, value, _ = definitions[2]
            definitions[2] = (name, value, 0x80 if weak else 0x200)
        if extra_atom:
            definitions.append(('__GLOBAL__D_a', 0x1040, 0))
        if alias:
            definitions.append(('_unrelated_alias', 0x1020, 0))
        command_bytes = 72 + 3 * 80 + 24
        text_offset, text_size = 32 + command_bytes, 16 * len(definitions)
        init_offset, term_offset = text_offset + text_size, text_offset + text_size + 16
        symbols_offset = term_offset + 16
        strings, string_indices = b'\0', []
        for name, _, _ in definitions:
            string_indices.append(len(strings))
            strings += name.encode() + b'\0'
        result = bytearray(struct.pack('<8I', 0xfeedfacf, 0x01000007, 3, 11, 2, command_bytes, 0, 0))
        result.extend(struct.pack('<II16sQQQQIIII', 0x19, 72 + 240, b'', 0, 0, 0, 0, 7, 7, 3, 0))
        for name, segment, address, size, offset, flags in [
            (b'__text', b'__TEXT', 0x1000, text_size, text_offset, 0x80000400),
            (b'__mod_init_func', b'__DATA', 0x2000, 16, init_offset,
             metaclass.LOADER_TYPES['__mod_init_func']),
            (b'__mod_term_func', b'__DATA', 0x2100, 16, term_offset,
             metaclass.LOADER_TYPES['__mod_term_func'])]:
            result.extend(struct.pack('<16s16sQQIIIIIIII', name, segment, address, size,
                                      offset, 3, 0, 0, flags, 0, 0, 0))
        result.extend(struct.pack('<6I', 2, 24, symbols_offset, len(definitions),
                                  symbols_offset + 16 * len(definitions), len(strings)))
        result.extend((b'\xc3' + b'\x90' * 15) * len(definitions))
        terms = [0x1030, 0x1020] if reverse_terms else [0x1020, 0x1030]
        if duplicate_pointer:
            terms[1] = terms[0]
        if interior:
            terms[0] += 1
        result.extend(struct.pack('<4Q', 0x1000, 0x1010, *terms))
        for index, (_, value, descriptor) in enumerate(definitions):
            result.extend(struct.pack('<IBBHQ', string_indices[index], 0x0e, 1, descriptor, value))
        result.extend(strings)
        return result
    with tempfile.TemporaryDirectory(prefix='s540-native-image-plan-') as temporary:
        folder = Path(temporary)
        for reverse in (False, True):
            path = folder / ('duplicate-local-finalizers-' + str(reverse))
            path.write_bytes(loader_fixture(reverse_terms=reverse))
            verified = verify_final_loader_pointers(path, loader_expected)
            assert len(verified['exact_distinct_code_atoms']) == 4
            assert Counter(name for _, name in verified['entries'])['__GLOBAL__D_a'] == 2
            checks += 1
        for label, options, phrase in [
            ('reused-finalizer', {'duplicate_pointer': True}, 'reuse one code atom'),
            ('extra-same-name-atom', {'extra_atom': True}, 'named-atom multiplicity'),
            ('aliased-finalizer', {'alias': True}, 'ambiguous aliases'),
            ('interior-finalizer', {'interior': True}, 'exact previously reviewed entry'),
            ('weak-finalizer', {'weak': True}, 'weak, alternate'),
            ('alternate-finalizer', {'alternate': True}, 'weak, alternate')]:
            path = folder / label
            path.write_bytes(loader_fixture(**options))
            try:
                verify_final_loader_pointers(path, loader_expected)
            except ValueError as error:
                assert phrase in str(error), str(error)
                checks += 1
            else:
                raise AssertionError('Invalid duplicate-local-name loader proof accepted: ' + label)
        for kind in (1, 11):
            path = folder / ('roots-' + str(kind))
            path.write_bytes(root_fixture(kind))
            assert verify_roots(path, expected_type=kind)['root_count'] == 25
            checks += 1
        for label, kind, options, phrase in [
            ('wrong-final-pointer', 11, {'bad_pointer': True}, 'exact resolved text address'),
            ('missing-object-slot', 1, {'missing_relocation': True}, 'exact pointer relocation'),
            ('data-replaces-code', 11, {'data_root': True}, 'not executable text')]:
            path = folder / label
            path.write_bytes(root_fixture(kind, **options))
            try:
                verify_roots(path, expected_type=kind)
            except ValueError as error:
                assert phrase in str(error), str(error)
                checks += 1
            else:
                raise AssertionError('Invalid actual root table accepted: ' + label)
        try:
            compilation_inputs(folder, {'status': 'compiled-full-original-source-only',
                'authoritative_darwin_execution': False, 'host_control': True}, original_units=True)
        except ValueError as error:
            assert 'native Apple compilation' in str(error)
            checks += 1
        else:
            raise AssertionError('Cross objects entered authoritative native link')
        (folder / 'composition.json').write_text('{"synthetic_control":true}\n')
        try:
            compilation_inputs(folder, {'status': 'compiled-full-original-source-only',
                'authoritative_darwin_execution': True, 'host_control': False,
                'composition_sha256': '0' * 64}, original_units=True)
        except ValueError as error:
            assert 'different exact source composition' in str(error)
            checks += 1
        else:
            raise AssertionError('A different source composition entered native link reuse')
    return {'format': 1, 'status': 'passed-source-plan-controls', 'checks': checks,
            'synthetic_root_pointer_fixtures': True, 'duplicate_local_finalizer_controls': True,
            'native_link_performed': False, **GATES}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--self-test', action='store_true')
    for name in ('upstream', 'v3-root', 'namespace', 'kernel-sdk', 'assets-dir', 'output'):
        parser.add_argument('--' + name, type=Path)
    parser.add_argument('--cc', type=Path, default=Path('/usr/bin/clang'))
    parser.add_argument('--cxx', type=Path, default=Path('/usr/bin/clang++'))
    parser.add_argument('--ld', type=Path)
    parser.add_argument('--sdk-archive', type=Path)
    parser.add_argument('--composition-dir', type=Path,
                        help='Inspect an existing exact source inventory in --plan-only mode; native builds always compile fresh.')
    parser.add_argument('--successor-manifest', type=Path)
    parser.add_argument('--project-successor-manifest', type=Path)
    parser.add_argument('--retained-diagnostic', action='store_true')
    parser.add_argument('--rc-participant', action='store_true')
    parser.add_argument('--shutdown-protocol', action='store_true')
    parser.add_argument('--platform-closure', action='store_true')
    parser.add_argument('--retained-backends', action='store_true')
    parser.add_argument('--global-epoch', action='store_true')
    parser.add_argument('--live-abi-closure', action='store_true')
    parser.add_argument('--plan-only', action='store_true')
    args = parser.parse_args()
    if args.self_test:
        print(json.dumps(self_test(), sort_keys=True))
        return 0
    for name in ('upstream', 'v3_root', 'namespace', 'kernel_sdk', 'assets_dir', 'output'):
        if getattr(args, name) is None:
            parser.error('--' + name.replace('_', '-') + ' is required')
    result = build(args)
    print(json.dumps({'status': result['status'], 'final_image': result.get('final_image'), **GATES}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
