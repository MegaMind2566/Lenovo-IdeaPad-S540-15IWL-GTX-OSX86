#!/usr/bin/env python3
"""Source-bound local depth proof for the two-function DSM remapping SCC.

Actual function bodies are executed with explicit external fixtures. The bound
is for these local recursive edges only, not callbacks from external callees.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

SOURCES = {
 'src/nvidia/src/kernel/platform/acpi_common.c': 'b382e8f0260c8d56be62b18e31d7a7f25e04e078bb29c4546c655c8f1ba1f94f',
 'src/nvidia/inc/kernel/platform/acpi_common.h': 'caa3efa1da4416ca0a200299be381444b4e1e2652d1324f3312cae946582f2b2',
 'src/nvidia/interface/nvacpitypes.h': '05d3023c8ea7dc41326f1324491880df70802d953faca19219f181d284a5e352',
 'src/nvidia/interface/acpigenfuncs.h': 'e558f7936d0886f1ee7686a0561c31ca055414c5ebfec335cef8546a9f42635b'}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def function(text, name):
    found = list(re.finditer(r'^NV_STATUS\s*\n' + name + r'\s*\(', text, re.M))
    if len(found) != 1:
        raise ValueError('Unique actual source function required: ' + name)
    start = found[0].start()
    opening = text.index('{', found[0].end())
    # Comments/strings are replaced with equal-length blanks before counting.
    stripped = re.sub(r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"',
                      lambda m: ' ' * len(m[0]), text, flags=re.S)
    depth = 0
    for index in range(opening, len(text)):
        depth += (stripped[index] == '{') - (stripped[index] == '}')
        if not depth:
            return text[start:index + 1]
    raise ValueError('Unterminated actual body: ' + name)


def fixture(texts, mutated=False):
    source, header, enum_header, generic = texts
    enum = re.search(r'typedef enum _ACPI_DSM_FUNCTION\s*\{.*?\}\s*ACPI_DSM_FUNCTION;',
                     enum_header, re.S)[0]
    table = re.search(r'static const ACPI_DSM_FUNCTION dsmOrderOfPrecedenceList\[\]\s*=.*?;',
                      source, re.S)[0]
    names = re.findall(r'ACPI_DSM_FUNCTION_\w+', table.split('=', 1)[1])
    if len(names) != 12 or len(set(names)) != 12:
        raise ValueError('Exact immutable twelve-entry DSM table required.')
    assertions = '\n'.join('_Static_assert(' + name + ' < ACPI_DSM_FUNCTION_COUNT, "concrete DSM table");'
                           for name in names)
    if mutated:
        table = table.replace(names[0], 'ACPI_DSM_FUNCTION_CURRENT', 1)
        assertions = ''
    macros = '\n'.join(re.search(r'^#define ' + name + r'\([^\n]+', header, re.M)[0]
                       for name in ('isGenericDsmFunction', 'isGenericDsmSubFunction'))
    definitions = '\n'.join(re.search(r'^#define ' + name + r'\s+[^\n]+', generic, re.M)[0]
                            for name in ('NV_ACPI_GENERIC_FUNC_START', 'NV_ACPI_GENERIC_FUNC_COUNT'))
    bodies = []
    for name in ('testIfDsmSubFunctionEnabled', 'remapDsmFunctionAndSubFunction'):
        body = function(source, name)
        bodies.append(body.replace(name, 'actual_' + name, 1))
    return r'''
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef uint32_t NvU32;
typedef unsigned NV_STATUS;
#define NV_OK 0
#define NV_ERR_INVALID_ARGUMENT 1
#define NV_ERR_NOT_SUPPORTED 2
#define NV_ERR_OPERATING_SYSTEM 3
#define NV_ERR_OBJECT_NOT_FOUND 4
#define DSM_FUNC_STATUS_OVERRIDE 0
#define DSM_FUNC_STATUS_SUCCESS 1
#define DSM_FUNC_STATUS_FAILED 2
#define DSM_FUNC_STATUS_UNKNOWN 3
#define NVBIT(x) (1U << (x))
#define NV_ARRAY_ELEMENTS(x) (sizeof(x)/sizeof((x)[0]))
#define NV_ASSERT_OR_RETURN(condition, status) do { if (!(condition)) return status; } while(0)
#define NV_PRINTF(...) ((void)0)
''' + enum + '\n' + definitions + '\n' + macros + '\n' + table + '\n' + assertions + r'''
typedef struct {
 struct { struct { unsigned suppFuncStatus, suppFuncsLen; unsigned char suppFuncs[8]; }
  dsm[ACPI_DSM_FUNCTION_COUNT]; unsigned dsmCurrentFuncSupport;
  ACPI_DSM_FUNCTION dsmCurrentFunc[8]; unsigned dsmCurrentSubFunc[8]; } acpi;
} OBJGPU;
static unsigned depth, peak, guardHits, cases, mapFailure;
static NV_STATUS testIfDsmSubFunctionEnabled(OBJGPU *, ACPI_DSM_FUNCTION, NvU32);
static NV_STATUS remapDsmFunctionAndSubFunction(OBJGPU *, ACPI_DSM_FUNCTION *, NvU32 *);
static NV_STATUS _getRemappedDsmSubfunction(ACPI_DSM_FUNCTION f, NvU32 s, NvU32 *out) {
 (void)f;
 /* Deliberately permits generic outputs too: the local depth proof must not
    assume an unproved scalar restriction on this external helper. */
 *out=s; return mapFailure ? NV_ERR_NOT_SUPPORTED : NV_OK;
}
''' + '\n'.join(bodies) + r'''
static NV_STATUS testIfDsmSubFunctionEnabled(OBJGPU *g, ACPI_DSM_FUNCTION f, NvU32 s) {
 ++depth; if(depth>peak) peak=depth;
 if(depth>4) { ++guardHits; --depth; return NV_ERR_NOT_SUPPORTED; }
 NV_STATUS result=actual_testIfDsmSubFunctionEnabled(g,f,s); --depth; return result;
}
static NV_STATUS remapDsmFunctionAndSubFunction(OBJGPU *g, ACPI_DSM_FUNCTION *f, NvU32 *s) {
 ++depth; if(depth>peak) peak=depth;
 if(depth>4) { ++guardHits; --depth; return NV_ERR_NOT_SUPPORTED; }
 NV_STATUS result=actual_remapDsmFunctionAndSubFunction(g,f,s); --depth; return result;
}
int main(void) {
 for(unsigned f=0;f<=ACPI_DSM_FUNCTION_CURRENT;++f)
 for(unsigned sub=0;sub<16;++sub)
 for(unsigned status=0;status<4;++status)
 for(unsigned cached=0;cached<2;++cached)
 for(mapFailure=0;mapFailure<2;++mapFailure)
 for(unsigned entry=0;entry<2;++entry) {
  OBJGPU gpu; memset(&gpu,0,sizeof(gpu));
  for(unsigned i=0;i<ACPI_DSM_FUNCTION_COUNT;++i) {
   gpu.acpi.dsm[i].suppFuncStatus=status; gpu.acpi.dsm[i].suppFuncsLen=7;
   memset(gpu.acpi.dsm[i].suppFuncs,255,8);
  }
  gpu.acpi.dsmCurrentFuncSupport=cached?255:0;
  for(unsigned i=0;i<8;++i) { gpu.acpi.dsmCurrentFunc[i]=ACPI_DSM_FUNCTION_NVOP;gpu.acpi.dsmCurrentSubFunc[i]=i; }
  ACPI_DSM_FUNCTION current=(ACPI_DSM_FUNCTION)f;
  unsigned s=sub<8?sub:NV_ACPI_GENERIC_FUNC_START+sub-8;
  if(entry) (void)testIfDsmSubFunctionEnabled(&gpu,current,s);
  else (void)remapDsmFunctionAndSubFunction(&gpu,&current,&s);
  ++cases;
 }
 printf("{\"cases\":%u,\"maximum_local_activations\":%u,\"depth_guard_hits\":%u}\n",cases,peak,guardHits);
 return depth!=0;
}
'''


def run(args):
    if args.output.exists():
        raise ValueError('Fresh depth evidence output required.')
    texts = []
    for name, expected in SOURCES.items():
        raw = (args.source / name).read_bytes()
        if sha(raw) != expected:
            raise ValueError('The reviewed recursive source dependency changed: ' + name)
        texts.append(raw.decode())
    args.output.mkdir(parents=True)
    observations = {}
    for variant in ('actual', 'generic-table-mutation'):
        path = args.output / (variant + '.c')
        path.write_text(fixture(texts, variant != 'actual'))
        binary = args.output / variant
        command = [str(args.cc), '-std=c11', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
                   '-fsanitize=undefined,address', '-fno-sanitize-recover=all', str(path), '-o', str(binary)]
        compiled = subprocess.run(command, text=True, capture_output=True, timeout=120)
        (args.output / (variant + '.compile.log')).write_text(compiled.stdout + compiled.stderr)
        if compiled.returncode:
            raise ValueError('Actual source-body depth control did not compile: ' + compiled.stderr[-3000:])
        environment = dict(os.environ)
        environment['ASAN_OPTIONS'] = 'detect_leaks=0:halt_on_error=1:abort_on_error=1'
        environment['UBSAN_OPTIONS'] = 'halt_on_error=1:abort_on_error=1'
        executed = subprocess.run([str(binary)], text=True, capture_output=True, timeout=60, env=environment)
        (args.output / (variant + '.run.log')).write_text(executed.stdout + executed.stderr)
        if executed.returncode:
            raise ValueError('Actual source-body depth control failed: ' + executed.stderr[-3000:])
        observations[variant] = json.loads(executed.stdout)
    if observations['actual']['maximum_local_activations'] != 4 or observations['actual']['depth_guard_hits']:
        raise ValueError('Actual remapping bodies violate the reviewed local depth bound.')
    if not observations['generic-table-mutation']['depth_guard_hits']:
        raise ValueError('Mutation control did not detect the required concrete-table invariant.')
    result = {'format': 1, 'status': 'source-bound-local-recursion-depth-established',
        'source_sha256': SOURCES, 'observations': observations,
        'component': ['remapDsmFunctionAndSubFunction', 'testIfDsmSubFunctionEnabled'],
        'maximum_simultaneous_local_activations': 4,
        'proof': [
            'Every immutable precedence-table value is a concrete DSM enum below ACPI_DSM_FUNCTION_COUNT.',
            'The only remap-to-test recursive edge passes a precedence-table value by value.',
            'The next test-to-remap activation therefore has a nongeneric DSM function.',
            'That remap returns through its nongeneric branch before reaching the remap-to-test edge.',
            'Entering test(Generic) permits test→remap→test(Concrete)→remap(Concrete): four local activations.'],
        'external_callees': 'Explicit fixtures; their own frames and callback reentry remain unbounded.',
        'stack_graph_rewritten': False, 'aggregate_stack_proven': False,
        'original_entry_admission': False, 'kernel_execution': False, 'gpu_access': False}
    (args.output / 'acpi-depth.json').write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source', 'cc', 'output'):
        parser.add_argument('--' + name, required=True, type=Path)
    value = run(parser.parse_args())
    print(json.dumps({'status': value['status'], 'observations': value['observations']}))
