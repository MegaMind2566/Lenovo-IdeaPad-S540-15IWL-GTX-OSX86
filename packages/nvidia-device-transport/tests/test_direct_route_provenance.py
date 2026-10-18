# SPDX-License-Identifier: MIT
"""Verify the pinned Apple source argument used by Direct DMA admission."""
import hashlib
import json
from pathlib import Path
import re
import unittest


PACKAGE = Path(__file__).resolve().parents[1]


class DirectRouteSourceTests(unittest.TestCase):
    def test_original_apple_copies_match_pinned_blobs(self):
        contract = json.loads((PACKAGE / 'DIRECT-ROUTE-CONTRACT.json').read_text())
        self.assertEqual(contract['commit'],
                         'f6217f891ac0bb64f3d375211650a4c1ff8ca1ea')
        self.assertTrue((PACKAGE / contract['license']).is_file())
        for source in contract['source_copies']:
            with self.subTest(source=source['source']):
                content = (PACKAGE / source['path']).read_bytes()
                self.assertEqual(hashlib.sha256(content).hexdigest(), source['sha256'])
                blob = b'blob ' + str(len(content)).encode() + b'\0' + content
                self.assertEqual(hashlib.sha1(blob).hexdigest(), source['git_blob'])

    def test_boot_decision_precedes_platform_publication(self):
        source = (PACKAGE / 'reference/IOPlatformExpert.cpp').read_text()
        self.assertEqual(source.count('IOMapper::setMapperRequired('), 1)
        decision = 'IOMapper::setMapperRequired(NULL != getProperty(kIOPlatformMapperPresentKey));'
        self.assertLess(source.index(decision), source.index('setPlatform( this );'))
        mapper = (PACKAGE / 'reference/IOMapper.cpp').read_text()
        writers = re.findall(r'IOMapper::gSystem\s*=\s*([^;]+);', mapper)
        self.assertEqual(writers, ['(IOMapper *) IOMapper::kUnknown', 'this',
                                   '(IOMapper *) kHasMapper', '(IOMapper *) kNoMapper'])

    def test_bypassed_resolves_and_rejects_a_real_mapper(self):
        source = (PACKAGE / 'reference/IODMACommand.cpp').read_text()
        self.assertIn('if (!mapper && (kUnmapped != MAPTYPE(mappingOptions))) {\n'
                      '\t\tIOMapper::checkForSystemMapper();\n'
                      '\t\tmapper = IOMapper::gSystem;', source)
        self.assertIn('case kBypassed:\n\t\tif (!mapper) {\n\t\t\tbreak;\n'
                      '\t\t}\n\t\treturn kIOReturnBadArgument;', source)
        header = (PACKAGE / 'reference/IOMapper.h').read_text()
        for state in ('kNoMapper  = 0', 'kUnknown   = 1', 'kHasMapper = 2',
                      'kWaitMask  = 3'):
            self.assertIn(state, header)
        mapper = (PACKAGE / 'reference/IOMapper.cpp').read_text()
        self.assertIn('while ((uintptr_t) IOMapper::gSystem & kWaitMask)', mapper)
        self.assertIn('sMapperLock.sleep(&IOMapper::gSystem);', mapper)


if __name__ == '__main__':
    unittest.main()
