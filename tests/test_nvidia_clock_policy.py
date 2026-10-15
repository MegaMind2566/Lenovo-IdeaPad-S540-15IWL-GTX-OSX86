#!/usr/bin/env python3
"""Compare the production clock policy with Python's exact integer arithmetic.

This host test does not call Darwin APIs, load kernel code, or access a GPU.
Native ABI linkage and the Darwin backends are checked separately in CI.
"""

from pathlib import Path
import os
import random
import shlex
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "packages/nvidia-os-adapter/src"
MAX_U64 = (1 << 64) - 1
MAX_U32 = (1 << 32) - 1
QUANTUM_NS = 1_000_000


class ClockPolicy(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shlex.split(os.environ.get("CXX", ""))
        if not compiler:
            selected = shutil.which("clang++") or shutil.which("c++")
            if not selected:
                raise RuntimeError("A host C++ compiler is required.")
            compiler = [selected]
        cls.temporary = tempfile.TemporaryDirectory(prefix="nvidia-clock-policy-")
        cls.addClassCleanup(cls.temporary.cleanup)
        directory = Path(cls.temporary.name)
        driver = directory / "clock-policy.cpp"
        cls.binary = directory / "clock-policy"
        driver.write_text(r'''
#include "S540NvidiaClockPolicy.hpp"
#include <cinttypes>
#include <cstdio>
#include <type_traits>

using namespace S540NvidiaClock;
using Conversion = bool (*)(NvU64, NvU32, NvU32, NvU64 &);
static_assert(sizeof(NvU64) == 8 && alignof(NvU64) == 8,
              "NVIDIA's 64-bit ABI changed.");
static_assert(sizeof(NvU32) == 4 && std::is_unsigned<NvU32>::value,
              "NVIDIA's 32-bit ABI changed.");
static_assert(std::is_unsigned<NvU64>::value,
              "The uptime ABI must be unsigned.");
static_assert(std::is_same<decltype(&ticksToNanoseconds), Conversion>::value,
              "The production conversion signature changed.");
static_assert(std::is_same<decltype(coarseNanoseconds(NvU64(0))), NvU64>::value,
              "The ordinary clock must preserve its 64-bit result type.");
static_assert(kCoarseQuantumNS == 1000000ULL,
              "The declared software quantum changed.");

int main() {
    uint64_t ticks = 0;
    uint32_t numer = 0, denom = 0;
    int scanned = 0;
    while ((scanned = std::scanf("%" SCNu64 " %" SCNu32 " %" SCNu32,
                                &ticks, &numer, &denom)) == 3) {
        NvU64 result = ~NvU64(0);
        const bool valid = ticksToNanoseconds(static_cast<NvU64>(ticks),
                                              numer, denom, result);
        std::printf("%u %" PRIu64 " %" PRIu64 "\n", valid ? 1U : 0U,
                    static_cast<uint64_t>(result),
                    static_cast<uint64_t>(coarseNanoseconds(ticks)));
    }
    return scanned == EOF && !std::ferror(stdin) && !std::ferror(stdout) ? 0 : 2;
}
''', encoding="utf-8")
        subprocess.run([*compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror",
                        "-O2", "-I", str(SOURCE), str(driver), "-o", str(cls.binary)],
                       check=True, timeout=30, capture_output=True, text=True)

    def test_conversion_and_quantization_match_exact_integer_oracle(self):
        cases = [
            (0, 1, 1), (1, 1, 1), (MAX_U64, 1, 1),
            (MAX_U64, MAX_U32, MAX_U32),
            (MAX_U64 - 1, MAX_U32, MAX_U32),
            (MAX_U64, 1, MAX_U32), (MAX_U64, MAX_U32, 1),
            (1, MAX_U32, MAX_U32 - 1),
            (0, 0, 1), (0, 1, 0), (MAX_U64, 0, MAX_U32),
            (MAX_U64, MAX_U32, 0), (MAX_U64, 0, 0),
        ]
        # Values on either side of the actual 64-bit result boundary cover
        # both whole-product overflow and overflow from the remainder term.
        for numer, denom in ((3, 2), (4, 3), (MAX_U32, MAX_U32 - 1),
                             (MAX_U32, 1), (1, MAX_U32)):
            boundary = min(MAX_U64, MAX_U64 * denom // numer)
            for delta in (-2, -1, 0, 1, 2):
                ticks = boundary + delta
                if 0 <= ticks <= MAX_U64:
                    cases.append((ticks, numer, denom))
        for ticks in (0, 1, QUANTUM_NS - 1, QUANTUM_NS, QUANTUM_NS + 1,
                      2 * QUANTUM_NS - 1, MAX_U64):
            cases.append((ticks, 1, 1))
        generator = random.Random(0x540C10C)
        cases.extend((generator.getrandbits(64), generator.getrandbits(32),
                      generator.getrandbits(32)) for _ in range(1024))
        completed = subprocess.run([str(self.binary)],
            input="".join(f"{ticks} {numer} {denom}\n" for ticks, numer, denom in cases),
            check=True, timeout=10, capture_output=True, text=True)
        lines = completed.stdout.splitlines()
        self.assertEqual(len(lines), len(cases))
        for parameters, line in zip(cases, lines):
            ticks, numer, denom = parameters
            expected = ticks * numer // denom if numer and denom else None
            valid = expected is not None and expected <= MAX_U64
            with self.subTest(ticks=ticks, numer=numer, denom=denom):
                self.assertEqual(tuple(map(int, line.split())),
                    (int(valid), expected if valid else 0,
                     ticks // QUANTUM_NS * QUANTUM_NS))


if __name__ == "__main__":
    unittest.main()
