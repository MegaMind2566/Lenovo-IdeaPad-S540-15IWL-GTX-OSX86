#!/usr/bin/env python3
"""Compile and exercise the inventory's actual portable C parsing helpers.

These checks do not simulate IOKit or establish visibility on the target laptop.
The native workflow separately builds and runs the real macOS program.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


SOURCE = (Path(__file__).resolve().parents[1] / "packages" / "nvidia-pci" /
          "src" / "nvidia_pci_inventory.c")

HARNESS = r'''
#define NVIDIA_PCI_CORE_TEST
#include SOURCE_PATH
#include <assert.h>

static size_t from_hex(const char *text, unsigned char *bytes, size_t capacity)
{
    size_t length = strlen(text);
    assert(length % 2 == 0 && length / 2 < capacity);
    for (size_t i = 0; i < length / 2; ++i) {
        unsigned int value;
        assert(sscanf(text + i * 2, "%2x", &value) == 1);
        bytes[i] = (unsigned char)value;
    }
    bytes[length / 2] = '\0';
    return length / 2;
}

int main(int argc, char **argv)
{
    assert(argc >= 3);
    unsigned char bytes[8192];
    size_t length = from_hex(argv[2], bytes, sizeof(bytes));
    if (strcmp(argv[1], "decode") == 0) {
        uint32_t value = UINT32_C(0xabcdef01);
        if (pci_decode_le32(bytes, length, &value))
            printf("%" PRIu32 "\n", value);
        else {
            assert(value == UINT32_C(0xabcdef01));
            puts("invalid");
        }
        assert(!pci_decode_le32(NULL, 4, &value));
        assert(!pci_decode_le32(bytes, 4, NULL));
    } else if (strcmp(argv[1], "json") == 0) {
        json_string(stdout, (const char *)bytes);
        putchar('\n');
    } else if (strcmp(argv[1], "token") == 0) {
        assert(argc == 4);
        printf("%d\n", has_boot_token((const char *)bytes, argv[3]));
    } else {
        return 64;
    }
    return fflush(stdout) == 0 ? 0 : 1;
}
'''


class InventoryCoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        compiler = os.environ.get("CC") or shutil.which("clang") or shutil.which("cc")
        if not compiler:
            raise RuntimeError("A C compiler is required for the inventory checks.")
        cls.temporary = tempfile.TemporaryDirectory(prefix="nvidia-pci-core-")
        directory = Path(cls.temporary.name)
        harness = directory / "core.c"
        harness.write_text(HARNESS.replace("SOURCE_PATH", json.dumps(str(SOURCE))))
        cls.executable = directory / "core"
        subprocess.run([
            compiler, "-std=c11", "-Wall", "-Wextra", "-Werror", "-O1", "-g",
            "-fsanitize=address,undefined", "-fno-omit-frame-pointer",
            str(harness), "-o", str(cls.executable),
        ], check=True)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def run_helper(self, operation: str, value: bytes, *arguments: str) -> str:
        environment = os.environ.copy()
        # The helpers allocate no heap objects. LeakSanitizer's process tracing
        # is unavailable in some containers; address/undefined checks stay on.
        environment["ASAN_OPTIONS"] = "detect_leaks=0"
        result = subprocess.run(
            [str(self.executable), operation, value.hex(), *arguments],
            check=True, capture_output=True, text=True, env=environment)
        self.assertEqual(result.stderr, "")
        return result.stdout.strip()

    def test_exact_little_endian_identity_width(self) -> None:
        for value in (0, 0x10de, 0x1f91, 0x060400, 0x12345678, 0xffffffff):
            self.assertEqual(self.run_helper("decode", value.to_bytes(4, "little")),
                             str(value))
        for length in (0, 1, 2, 3, 5, 8, 16):
            self.assertEqual(self.run_helper("decode", b"\xff" * length), "invalid")

    def test_json_controls_quotes_and_backslashes(self) -> None:
        text = bytes(range(1, 128))
        encoded = self.run_helper("json", text)
        self.assertEqual(json.loads(encoded), text.decode("ascii"))
        self.assertTrue(encoded.isascii())
        self.assertNotIn("\n", encoded)

    def test_valid_unicode_and_invalid_utf8_remain_valid_json(self) -> None:
        for text in ("", "PCI0/RP05/PXSX", "é中文", "GPU 🚀"):
            encoded = self.run_helper("json", text.encode())
            self.assertEqual(json.loads(encoded), text)
            self.assertTrue(encoded.isascii())
        for raw in (b"\x80", b"\xc0\xaf", b"\xed\xa0\x80", b"\xf4\x90\x80\x80",
                    b"\xc2", b"\xe2\x82", b"\xf0\x9f\x92", b"\xffGPU"):
            encoded = self.run_helper("json", raw)
            decoded = json.loads(encoded)
            self.assertIn("\ufffd", decoded)
            self.assertTrue(encoded.isascii())

    def test_boot_argument_requires_an_exact_token(self) -> None:
        for text in (b"-wegnoegpu", b"-v -wegnoegpu keepsyms=1", b"\t-wegnoegpu\r\n",
                     b"-wegnoegpu   "):
            self.assertEqual(self.run_helper("token", text, "-wegnoegpu"), "1")
        for text in (b"", b"   ", b"-wegnoegpu=1", b"x-wegnoegpu", b"-wegnoegpux",
                     b"name=-wegnoegpu", b"-wegnoigpu"):
            self.assertEqual(self.run_helper("token", text, "-wegnoegpu"), "0")


if __name__ == "__main__":
    unittest.main()
