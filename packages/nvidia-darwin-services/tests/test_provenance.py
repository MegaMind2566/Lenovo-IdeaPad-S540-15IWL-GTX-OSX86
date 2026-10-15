# SPDX-License-Identifier: MIT
import hashlib
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


class Provenance(unittest.TestCase):
    def test_pinned_references(self):
        record = json.loads((ROOT / 'PROVENANCE.json').read_text())
        self.assertEqual(record['nvidia_commit'], '1a82fbfda8f321b056eb3568850f9316c5e465c5')
        self.assertEqual(len(record['reference_files']), 6)
        for item in record['reference_files']:
            data = (ROOT / item['local']).read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(), item['sha256'])

    def test_exact_nvidia_function_signatures(self):
        pattern = re.compile(r'\b(NV_STATUS|NvU(?:32|64)|NvBool|void\s*\*?)\s*NV_API_CALL\s+(\w+)\s*\(([^;]+)\)\s*;')
        def types(arguments):
            arguments = arguments.replace('RsAccessRight accessRight', 'NvU16').replace('NvU16 accessRight', 'NvU16')
            normalized = []
            for argument in arguments.split(','):
                argument = re.sub(r'(?<=\*)\s*[A-Za-z_]\w*\s*$', '', argument)
                argument = re.sub(r'\b(Nv\w+|RsAccessRight)\s+[A-Za-z_]\w*\s*$', r'\1', argument)
                normalized.append(re.sub(r'\s+', '', argument))
            return ','.join(normalized)
        upstream = {name: (re.sub(r'\s+', '', result), types(args))
                    for result, name, args in pattern.findall((ROOT / 'reference/os-interface.h').read_text())}
        public = [(name, (re.sub(r'\s+', '', result), types(args)))
                  for result, name, args in pattern.findall((ROOT / 'src/S540NvidiaDarwinServices.h').read_text())]
        self.assertGreaterEqual(len(public), 40)
        for name, signature in public:
            self.assertTrue(name.startswith('s540Darwin_os_'))
            self.assertEqual(signature, upstream[name.removeprefix('s540Darwin_')], name)

    def test_source_backed_cpu_spi(self):
        self.assertIn('extern int      cpu_number(void);', (ROOT / 'reference/apple-cpu-number.h').read_text())
        self.assertIn('_cpu_number', (ROOT / 'reference/apple-unsupported-x86_64.exports').read_text().splitlines())
        source = (ROOT / 'src/S540NvidiaDarwinProcess.cpp').read_text()
        self.assertIn('extern "C" int cpu_number(void);', source)
        self.assertIn('const int number = cpu_number();', source)
        self.assertNotIn('rdtscp', source.lower())

    def test_no_v9_symbol_override(self):
        for source in (ROOT / 'src').glob('*.cpp'):
            self.assertNotRegex(source.read_text(), r'extern\s+"C"[^\n]*\bos_(?:alloc|free|acquire|release|get|queue)_\w+\s*\(')

    def test_serialized_real_kernel_callbacks(self):
        for filename in ('S540NvidiaDarwinWork.cpp', 'S540NvidiaDarwinTimer.cpp'):
            source = (ROOT / 'src' / filename).read_text()
            self.assertIn('THREAD_CALL_OPTIONS_ONCE', source)
            self.assertIn('thread_call_cancel_wait', source)
            self.assertIn('thread_call_free', source)

    def test_wake_before_block_is_closed(self):
        source = (ROOT / 'src/S540NvidiaDarwinPlatform.cpp').read_text()
        self.assertLess(source.index('wait_result_t result = assert_wait'), source.index('if (result == THREAD_WAITING) result = thread_block'))
        self.assertIn('thread_wakeup_prim', source)
        self.assertIn('THREAD_ABORTSAFE : THREAD_UNINT', source)

    def test_no_device_side_effects(self):
        for source in (ROOT / 'src').glob('*.cpp'):
            self.assertNotRegex(source.read_text(), r'\b(?:registerInterrupt|pciConfigWrite\w*|writeConfig\w*|OSWriteLittleInt\w*)\s*\(')

    def test_full_apple_license_preserved(self):
        license_text = (ROOT / 'reference/APPLE_LICENSE').read_text()
        self.assertIn('APPLE PUBLIC SOURCE LICENSE', license_text)
        self.assertIn('Version 2.0', license_text)


if __name__ == '__main__':
    unittest.main()
