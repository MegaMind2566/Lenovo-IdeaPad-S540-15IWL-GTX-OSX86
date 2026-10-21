import importlib.util
from pathlib import Path
import unittest

SPEC = importlib.util.spec_from_file_location('switch_control',
    Path(__file__).resolve().parents[1] / 'check_switch_control.py')
switch = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(switch)


def fixture():
    text = bytearray(200)
    guard = (bytes.fromhex('41ffce4183fe04' '0f87') + (27).to_bytes(4, 'little', signed=True) +
             bytes.fromhex('488d05') + (70).to_bytes(4, 'little', signed=True) +
             bytes.fromhex('4a630cb04801c1ffe1'))
    text[10:39] = guard
    for i, target in enumerate((60, 64, 68, 72, 76)):
        text[100 + i*4:104 + i*4] = (target - 100).to_bytes(4, 'little', signed=True)
    instructions = [{'address': 17, 'mnemonic': 'ja', 'operands': '0x32'},
                    {'address': 37, 'mnemonic': 'jmpq', 'operands': '*%rcx'},
                    {'address': 50, 'mnemonic': 'nop', 'operands': ''},
                    *({'address': target, 'mnemonic': 'nop', 'operands': ''}
                      for target in (60, 64, 68, 72, 76)),
                    {'address': 80, 'mnemonic': 'jmp', 'operands': '0x3c'},
                    *({'address': 100 + 4*i, 'mnemonic': '<undecoded>', 'operands': '.long'}
                      for i in range(5))]
    return text, instructions


class SwitchProofControls(unittest.TestCase):
    def check(self, text, instructions, entries=((100, 20, 4),)):
        return switch.guarded_table(text, 0, 200, 37, instructions, [], entries)

    def test_all_targets_are_local_and_data_sites_are_explicit(self):
        result = self.check(*fixture())
        self.assertEqual(result['table_destinations'], [60, 64, 68, 72, 76])
        self.assertEqual(result['new_inter_function_call_edges'], 0)
        self.assertEqual(len(result['resolved_barriers']), 6)

    def test_unidentified_or_truncated_data_stays_unknown(self):
        for entries in ([], [(100, 16, 4)], [(100, 20, 1)]):
            with self.assertRaisesRegex(ValueError, 'LC_DATA_IN_CODE'):
                self.check(*fixture(), entries)

    def test_outside_target_or_guard_bypass_is_rejected(self):
        text, instructions = fixture()
        text[100:104] = (200).to_bytes(4, 'little', signed=True)
        with self.assertRaisesRegex(ValueError, 'same function'):
            self.check(text, instructions)
        text, instructions = fixture()
        instructions.append({'address': 2, 'mnemonic': 'jmp', 'operands': '0x18'})
        with self.assertRaisesRegex(ValueError, 'bypasses'):
            self.check(text, instructions)

    def test_different_index_or_another_indirect_transfer_is_rejected(self):
        text, instructions = fixture()
        text[34] ^= 1
        with self.assertRaisesRegex(ValueError, 'encoding'):
            self.check(text, instructions)
        text, instructions = fixture()
        instructions.append({'address': 45, 'mnemonic': 'callq', 'operands': '*%rax'})
        with self.assertRaisesRegex(ValueError, 'Another indirect'):
            self.check(text, instructions)


if __name__ == '__main__':
    unittest.main()
