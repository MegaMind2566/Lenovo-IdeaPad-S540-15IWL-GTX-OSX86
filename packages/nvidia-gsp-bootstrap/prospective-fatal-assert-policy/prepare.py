#!/usr/bin/env python3
"""Exact optional fatal-invariant successor; ordinary NV_CHECK is unchanged."""
from pathlib import Path
import hashlib
import json
import re

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p/'builders/check_nvidia_execution.py').is_file())
HEADER = 'src/nvidia/inc/libraries/utils/nvassert.h'
SOURCE = 'src/nvidia/src/libraries/utils/nvassert.c'
PROFILE = 'S540_NVIDIA_FATAL_ASSERT_POLICY'
FUNCTIONS = ('nvAssertFailed', 'nvAssertOkFailed', 'nvAssertFailedNoLog', 'nvAssertOkFailedNoLog')


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def function_span(text, name):
    matches = list(re.finditer(r'^void\s*\n' + re.escape(name) + r'\s*\(', text, re.M))
    if len(matches) != 1:
        raise ValueError('Expected one original assertion helper: ' + name)
    opening = text.index('{', matches[0].end())
    depth = 1
    tokens = re.compile(r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|[{}]', re.S)
    for token in tokens.finditer(text, opening + 1):
        depth += (token[0] == '{') - (token[0] == '}')
        if not depth:
            return matches[0].start(), token.end(), opening
    raise ValueError('Unclosed assertion helper')


HEADER_POLICY = r'''
/* Selected fatal-invariant diagnostic policy. This is deliberately stronger
 * than upstream's release assertions. It is not an OOM recovery or stack guard.
 * Bypass the pre-helper NVLOG call as well as journal/backtrace recursion. */
#if !defined(S540_NVIDIA_FATAL_ASSERT_POLICY) || S540_NVIDIA_FATAL_ASSERT_POLICY != 1
#error "Explicit immutable fatal assertion policy required"
#endif
#if !defined(NVRM) || !NVOS_IS_UNIX || NVOS_IS_LIBOS || defined(GSP_PLUGIN_BUILD) || defined(NVWATCH) || defined(NV_MODS)
#error "Fatal assertion policy requires the reviewed original Unix RM profile"
#endif
#if !(NV_PRINTF_ENABLED || NV_JOURNAL_ASSERT_ENABLE)
#error "Fatal assertion helpers must be enabled"
#endif
void nvAssertFailed(NV_ASSERT_FAILED_FUNC_TYPE) __attribute__((noreturn));
void nvAssertOkFailed(NvU32 status NV_ASSERT_FAILED_FUNC_COMMA_TYPE) __attribute__((noreturn));
void nvAssertFailedNoLog(NV_ASSERT_FAILED_FUNC_TYPE) __attribute__((noreturn));
void nvAssertOkFailedNoLog(NvU32 status NV_ASSERT_FAILED_FUNC_COMMA_TYPE) __attribute__((noreturn));
#undef NV_ASSERT_FAILED
#define NV_ASSERT_FAILED(exprStr) \
    do { nvAssertFailedNoLog(NV_ASSERT_FAILED_FUNC_PARAM(exprStr)); } while (0)
#undef NV_ASSERT_OK_FAILED
#define NV_ASSERT_OK_FAILED(exprStr, status) \
    do { nvAssertOkFailedNoLog(status NV_ASSERT_FAILED_FUNC_COMMA_PARAM(exprStr)); } while (0)
#undef NV_ASSERT_FAILED_FUNC
#define NV_ASSERT_FAILED_FUNC(exprStr) \
    do { nvAssertFailed(NV_ASSERT_FAILED_FUNC_PARAM(exprStr)); } while (0)
#undef NV_ASSERT_OK_FAILED_FUNC
#define NV_ASSERT_OK_FAILED_FUNC(exprStr, status) \
    do { nvAssertOkFailed(status NV_ASSERT_FAILED_FUNC_COMMA_PARAM(exprStr)); } while (0)
'''


def overlay(files):
    contract = json.loads((HERE/'SOURCE-CONTRACT.json').read_text())
    if set(files) != {HEADER, SOURCE}:
        raise ValueError('Exact assertion source/header pair required')
    for name, text in files.items():
        if sha(text) != contract['original_source_sha256'][name]:
            raise ValueError('Original complete assertion source changed: ' + name)
    result = dict(files)
    marker = '\n#ifdef __cplusplus\n}\n#endif //__cplusplus\n'
    if result[HEADER].count(marker) != 1:
        raise ValueError('Assertion header C linkage boundary changed')
    result[HEADER] = result[HEADER].replace(marker, '\n' + HEADER_POLICY + marker)
    text = result[SOURCE]
    for name in FUNCTIONS:
        start, end, opening = function_span(text, name)
        code = 'status' if 'OkFailed' in name else '0'
        body = '''{
    /* The selected invariant is terminal before any printf, NVLOG, journal,
     * backtrace or observer. os_bug_check reaches Darwin panic; trap is only
     * a non-returning backstop against a defective returning implementation. */
    (void)lineNum;
#if NV_ASSERT_FAILED_USES_STRINGS
    (void)pszFileName;
    os_bug_check(CODE, pszExpr ? pszExpr : "RM assertion failed");
#else
    os_bug_check(CODE, "RM assertion failed");
#endif
    __builtin_trap();
}'''.replace('CODE', code)
        text = text[:opening] + body + text[end:]
    result[SOURCE] = text
    expected = contract.get('successor_source_sha256')
    if expected and expected != {name: sha(text) for name, text in result.items()}:
        raise ValueError('Exact assertion policy successor changed')
    return result


def prepare(upstream, output):
    files = {name: (upstream/name).read_text() for name in (HEADER, SOURCE)}
    result = overlay(files)
    output.mkdir(parents=True, exist_ok=False)
    for name, text in result.items():
        path = output/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return result
