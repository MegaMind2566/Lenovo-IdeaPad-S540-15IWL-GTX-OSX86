#!/usr/bin/env python3
"""Check the exact-device gate and the two-register MMIO hardware boundary.

These tests do not load a kext. Native SDK compilation and linkage are separate
CI checks; a passing host policy test is not evidence of hardware attachment.
"""

from pathlib import Path
import os
import plistlib
import re
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "packages/nvidia-transport"
SOURCE = PACKAGE / "src/S540NvidiaPCIProbe.cpp"
HEADER = PACKAGE / "src/S540NvidiaPCIProbe.hpp"


def without_comments(source):
    return re.sub(r"/\*.*?\*/|//[^\n]*", "", source, flags=re.S)


class KernelBoundary(unittest.TestCase):
    def test_runtime_identity_rejects_every_single_bit_mismatch(self):
        """A near-match, unavailable config, or swapped subsystem cannot attach."""
        compiler = os.environ.get("CXX") or shutil.which("clang++") or shutil.which("c++")
        self.assertTrue(compiler, "A host C++ compiler is required for the identity policy test.")
        program = r'''
#include "S540NvidiaPCIProbe.hpp"
using namespace S540NvidiaPCIProbePolicy;
int main() {
    const Identity exact = {0x1f9110deU, 0x030000a1U, 0x380617aaU};
    if (!matches(exact)) return 1;
    for (unsigned int field = 0; field < 3; ++field) {
        for (unsigned int bit = 0; bit < 32; ++bit) {
            Identity changed = exact;
            uint32_t *word = field == 0 ? &changed.vendorDevice
                : field == 1 ? &changed.revisionClass : &changed.subsystem;
            *word ^= uint32_t(1) << bit;
            if (matches(changed)) return 2;
        }
    }
    const Identity unavailable[] = {
        {0xffffffffU, 0xffffffffU, 0xffffffffU},
        {0x1f91ffffU, 0x030000a1U, 0x380617aaU},
        {0, 0, 0},
        {0x1f9110deU, 0x030000a1U, 0x17aa3806U},
        {0x1f9110deU, 0x030200a1U, 0x380617aaU},
        {0x1f9110deU, 0x030000a2U, 0x380617aaU}
    };
    for (unsigned int i = 0; i < sizeof(unavailable) / sizeof(unavailable[0]); ++i)
        if (matches(unavailable[i])) return 3;
    return 0;
}
'''
        with tempfile.TemporaryDirectory(prefix="nvidia-transport-policy-") as directory:
            source = Path(directory) / "policy.cpp"
            binary = Path(directory) / "policy"
            source.write_text(program, encoding="utf-8")
            subprocess.run([compiler, "-std=c++11", "-Wall", "-Wextra", "-Werror",
                            "-I", str(HEADER.parent), str(source), "-o", str(binary)],
                           check=True, timeout=30, capture_output=True, text=True)
            subprocess.run([str(binary)], check=True, timeout=10)

    def test_mmio_bar_power_and_decode_policy_negative_cases(self):
        compiler = os.environ.get("CXX") or shutil.which("clang++") or shutil.which("c++")
        self.assertTrue(compiler, "A host C++ compiler is required.")
        program = r'''
#include "S540NvidiaPCIProbe.hpp"
#include <cstring>
using namespace S540NvidiaPCIProbePolicy;
struct Config {
    uint32_t words[64];
    unsigned int count;
    bool badOffset;
    Config() : words{}, count(0), badOffset(false) {
        words[1] = 0x00100002; // Capability list + already enabled memory decode.
        words[3] = 0; // Normal header.
        words[0x34 / 4] = 0x40;
        words[0x40 / 4] = 0x00030001; // PM version 3, list terminator.
    }
    bool operator()(uint32_t offset, uint32_t &value) {
        ++count;
        if (offset > 0xfc || (offset & 3) != 0) { badOffset = true; return false; }
        value = words[offset / 4];
        return value != UINT32_MAX;
    }
};
bool is(const char *value, const char *expected) {
    return value && std::strcmp(value, expected) == 0;
}
int main() {
    if (validateBar0(0x90000000, 0x02010010, 0x90000000, 0x1000000)) return 1;
    for (uint32_t flags = 1; flags < 16; ++flags)
        if (!is(validateBar0(0x90000000 | flags, 0x02010010, 0x90000000, 0x1000000),
                "bar0-configuration-invalid")) return 2;
    const uint32_t invalidBars[] = {0, UINT32_MAX};
    for (unsigned int i = 0; i < 2; ++i)
        if (!is(validateBar0(invalidBars[i], 0x02010010, 0x90000000, 0x1000000),
                "bar0-configuration-invalid")) return 3;
    const uint64_t invalidTags[] = {0x02010014, 0x01010010, 0x03010010, 0x42010010};
    for (unsigned int i = 0; i < 4; ++i)
        if (!is(validateBar0(0x90000000, invalidTags[i], 0x90000000, 0x1000000),
                "bar0-descriptor-invalid")) return 4;
    const uint64_t invalidAddresses[] = {0, 0x90000004, 0x91000000, 0x190000000};
    for (unsigned int i = 0; i < 4; ++i)
        if (!is(validateBar0(0x90000000, 0x02010010, invalidAddresses[i], 0x1000000),
                "bar0-descriptor-invalid")) return 5;
    if (!validateBar0(0x90000000, 0x02010010, 0x90000000, 4)
        || !validateBar0(0x90000000, 0x02010010, 0x90000000, 0x2000000)) return 6;
    Config d0;
    if (requireD0(d0) || d0.badOffset || d0.count != 5) return 7;
    for (unsigned int state = 1; state < 4; ++state) {
        Config cfg; cfg.words[0x44 / 4] = state;
        if (!is(requireD0(cfg), "pci-not-d0")) return 8;
    }
    for (unsigned int version = 0; version < 8; ++version) {
        Config cfg; cfg.words[0x40 / 4] = (version << 16) | 1;
        const char *result = requireD0(cfg);
        if (version >= 1 && version <= 3 ? result != nullptr
            : !is(result, "pm-capability-unsupported")) return 9;
    }
    Config noList; noList.words[1] = 2;
    if (!is(requireD0(noList), "pm-capability-unavailable")) return 10;
    Config wrongHeader; wrongHeader.words[3] = 0x00010000;
    if (!is(requireD0(wrongHeader), "pm-capability-malformed")) return 11;
    Config multiFunction; multiFunction.words[3] = 0x00800000;
    if (requireD0(multiFunction)) return 12;
    const uint32_t invalidPointers[] = {0x3c, 0x41, 0xfd, 0xff};
    for (unsigned int i = 0; i < 4; ++i) {
        Config cfg; cfg.words[0x34 / 4] = invalidPointers[i];
        if (!is(requireD0(cfg), "pm-capability-malformed") || cfg.badOffset) return 13;
    }
    Config end; end.words[0x40 / 4] = 5;
    if (!is(requireD0(end), "pm-capability-unavailable")) return 14;
    Config self; self.words[0x40 / 4] = 0x4005;
    if (!is(requireD0(self), "pm-capability-malformed") || self.count != 4) return 15;
    Config cycle; cycle.words[0x40 / 4] = 0x4805; cycle.words[0x48 / 4] = 0x4005;
    if (!is(requireD0(cycle), "pm-capability-malformed") || cycle.count != 5) return 16;
    Config truncated; truncated.words[0x34 / 4] = 0xfc; truncated.words[0xfc / 4] = 0x30001;
    if (!is(requireD0(truncated), "pm-capability-malformed") || truncated.badOffset) return 17;
    const uint32_t unavailableOffsets[] = {0x04, 0x0c, 0x34, 0x40, 0x44};
    for (unsigned int i = 0; i < 5; ++i) {
        Config cfg; cfg.words[unavailableOffsets[i] / 4] = UINT32_MAX;
        if (!is(requireD0(cfg), "pci-config-unavailable") || cfg.badOffset) return 18;
    }
    Config longest;
    for (uint32_t offset = 0x40; offset <= 0xfc; offset += 4)
        longest.words[offset / 4] = (offset < 0xfc ? (offset + 4) << 8 : 0) | 5;
    if (!is(requireD0(longest), "pm-capability-malformed") || longest.count != 51
        || longest.badOffset) return 19;
    const uint32_t normalTU117 = 0x167000a1;
    if (architecture(normalTU117) != 0x16 || implementation(normalTU117) != 7
        || !is(identifyBoot0(normalTU117), "tu117-identified")) return 20;
    if (architecture(normalTU117 | 0x100) != 0x36
        || !is(identifyBoot0(normalTU117 | 0x100), "architecture-mismatch")) return 21;
    if (!is(identifyBoot0(0), "zero-value")
        || !is(identifyBoot0(UINT32_MAX), "all-ones-value")
        || !is(identifyBoot0(0x166000a1), "implementation-mismatch")) return 22;
    // Stepping and other reserved bits are reported, not invented match gates.
    if (!is(identifyBoot0(0x16700002), "tu117-identified")) return 23;
    return 0;
}
'''
        with tempfile.TemporaryDirectory(prefix="nvidia-mmio-policy-") as directory:
            source = Path(directory) / "policy.cpp"
            binary = Path(directory) / "policy"
            source.write_text(program, encoding="utf-8")
            subprocess.run([compiler, "-std=c++11", "-Wall", "-Wextra", "-Werror",
                            "-I", str(HEADER.parent), str(source), "-o", str(binary)],
                           check=True, timeout=30, capture_output=True, text=True)
            subprocess.run([str(binary)], check=True, timeout=10)

    def test_boot42_decode_and_hal_selection_reject_other_chip_variants(self):
        compiler = os.environ.get("CXX") or shutil.which("clang++") or shutil.which("c++")
        self.assertTrue(compiler, "A host C++ compiler is required.")
        program = r'''
#include "S540NvidiaPCIProbe.hpp"
#include <cstring>
using namespace S540NvidiaPCIProbePolicy;
int main() {
    const uint32_t boot0 = 0x167000a1;
    // BOOT42 bit 8 belongs to lower register data, not architecture extension.
    const uint32_t boot42 = 0x167005a1;
    if (!boot42IsTU117(boot42) || boot42Architecture(boot42) != 0x16
        || boot42Implementation(boot42) != 7 || boot42ChipID(boot42) != 0x167
        || std::strcmp(identifyBoot42(boot42), "tu117-identified")
        || selectHALVariant(boot0, boot42) != 41) return 1;
    // Every other architecture/implementation combination must remain unselected.
    for (uint32_t architecture = 0; architecture < 64; ++architecture) {
        for (uint32_t implementation = 0; implementation < 16; ++implementation) {
            const uint32_t word = (architecture << 24) | (implementation << 20) | 0x5a1;
            const bool expected = architecture == 0x16 && implementation == 7;
            if (boot42Architecture(word) != architecture
                || boot42Implementation(word) != implementation
                || boot42ChipID(word) != (architecture << 4 | implementation)
                || boot42IsTU117(word) != expected
                || (selectHALVariant(boot0, word) == 41) != expected) return 2;
        }
    }
    const uint32_t invalidBoot0[] = {0, UINT32_MAX, 0x167001a1, 0x157000a1, 0x166000a1};
    for (unsigned int i = 0; i < 5; ++i)
        if (selectHALVariant(invalidBoot0[i], boot42) != -1) return 3;
    if (selectHALVariant(boot0, 0) != -1 || selectHALVariant(boot0, UINT32_MAX) != -1)
        return 4;
    if (std::strcmp(identifyBoot42(0), "zero-value")
        || std::strcmp(identifyBoot42(UINT32_MAX), "all-ones-value")
        || std::strcmp(identifyBoot42(0x367000a1), "architecture-mismatch")
        || std::strcmp(identifyBoot42(0x166000a1), "implementation-mismatch")) return 5;
    return 0;
}
'''
        with tempfile.TemporaryDirectory(prefix="nvidia-hal-policy-") as directory:
            source = Path(directory) / "policy.cpp"
            binary = Path(directory) / "policy"
            source.write_text(program, encoding="utf-8")
            subprocess.run([compiler, "-std=c++11", "-Wall", "-Wextra", "-Werror",
                            "-I", str(HEADER.parent), str(source), "-o", str(binary)],
                           check=True, timeout=30, capture_output=True, text=True)
            subprocess.run([str(binary)], check=True, timeout=10)

    def test_hardware_boundary_has_two_fixed_reads_and_no_write_or_power_helpers(self):
        code = without_comments(SOURCE.read_text(encoding="utf-8"))
        self.assertEqual(code.count("result.rawValue = *registerWord;"), 1)
        self.assertEqual(code.count("->createMappingInTask("), 1)
        self.assertIn("kIOMapAnywhere | kIOMapReadOnly | kIOMapInhibitCache | kIOMapUnique, Offset, 4", code)
        self.assertIn("const volatile uint32_t *registerWord", code)
        self.assertIn("static_assert(Offset == 0 || Offset == 0xa00,", code)
        self.assertEqual(re.findall(r"attemptRegisterRead<([^>]+)>\(device, bar0\)", code),
                         ["0", "0xa00"])
        self.assertRegex(code, r"result\.boot0\.readCount == 1\s*&& "
                         r"S540NvidiaPCIProbePolicy::boot0IsTU117\(result\.boot0\.rawValue\)\)\s*"
                         r"result\.boot42 = attemptRegisterRead<0xa00>")
        self.assertEqual(code.count("ScopedArbitration arbitration(device);"), 1)
        self.assertIn("mapping.reset();", code)
        self.assertIn('device->copyProperty("IODeviceMemory")', code)
        self.assertIn("value->lockForArbitration(false)", code)
        self.assertIn("provider->unlockForArbitration()", code)
        self.assertIn("device->isOpen()", code)
        self.assertEqual(code.count("checkReadPrerequisites(device, bar0)"), 2)
        self.assertIn("offset > 0xfc || (offset & 3U) != 0", code)
        self.assertNotRegex(code, r"\b(configWrite\w*|extendedConfig\w*|"
                            r"getDeviceMemoryWithRegister|getDeviceMemoryWithIndex|"
                            r"setTunnelL1Enable|setBusMasterEnable|setMemoryEnable|setIOEnable|"
                            r"setConfigBits|mapDeviceMemory\w*|IODMACommand|"
                            r"IOBufferMemoryDescriptor|IOInterruptEventSource|IOTimerEventSource|"
                            r"IOWorkLoop|evaluateObject|newUserClient|registerPowerDriver|PMinit|"
                            r"joinPMtree|setPowerState)\b")
        self.assertNotRegex(code, r"->(?:map|readBytes|writeBytes|read|write|open)\s*\(")
        self.assertNotRegex(code, r"(?m)^\s*\*registerWord\s*=")

    def test_personality_requires_exact_device_and_observational_category(self):
        with (PACKAGE / "Info.plist").open("rb") as stream:
            info = plistlib.load(stream)
        self.assertEqual(info["CFBundleIdentifier"], "org.osx86.S540NvidiaPCIProbe")
        self.assertEqual(info["CFBundleVersion"], "0.4.0")
        self.assertEqual(set(info["IOKitPersonalities"]), {"S540NvidiaPCIProbe"})
        personality = info["IOKitPersonalities"]["S540NvidiaPCIProbe"]
        self.assertEqual(personality, {
            "CFBundleIdentifier": info["CFBundleIdentifier"],
            "IOClass": "S540NvidiaPCIProbe",
            "IOMatchCategory": "S540NvidiaPCIProbe",
            "IOProviderClass": "IOPCIDevice",
            "IOPCIPrimaryMatch": "0x1f9110de",
            "IOPCISecondaryMatch": "0x380617aa",
            "IOPCIClassMatch": "0x03000000&0xffffff00",
        })
        self.assertEqual(set(info["OSBundleLibraries"]), {
            "com.apple.kpi.iokit", "com.apple.kpi.libkern",
            "com.apple.kpi.mach", "com.apple.iokit.IOPCIFamily"})


if __name__ == "__main__":
    unittest.main()
