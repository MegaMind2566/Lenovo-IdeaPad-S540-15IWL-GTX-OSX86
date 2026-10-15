#!/usr/bin/env python3
"""Check the exact-device gate and the prototype's hardware-access boundary.

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

    def test_hardware_access_is_fixed_config_reads_and_borrowed_metadata(self):
        code = without_comments(SOURCE.read_text(encoding="utf-8"))
        self.assertEqual(re.findall(r"device->configRead32\((0x[0-9a-f]+)\)", code),
                         ["0x00", "0x08", "0x2c", "0x04"])
        self.assertEqual(set(re.findall(r"device->(\w+)\s*\(", code)),
                         {"configRead32", "getProperty"})
        self.assertEqual(set(re.findall(r"memory->(\w+)\s*\(", code)),
                         {"getPhysicalAddress", "getLength", "getTag"})
        self.assertIn('device->getProperty("IODeviceMemory")', code)
        self.assertIn("count == 0 || count > 16", code)
        self.assertIn("OSDynamicCast(IOMemoryDescriptor, published->getObject(index))", code)
        self.assertIn("if (bars[barIndex])", code)
        self.assertNotRegex(code, r"provider->\w+\s*\(")
        self.assertNotRegex(code, r"\b(configWrite\w*|extendedConfigWrite\w*|"
                            r"getDeviceMemoryWithRegister|getDeviceMemoryWithIndex|"
                            r"setTunnelL1Enable|"
                            r"setBusMasterEnable|setMemoryEnable|setIOEnable|"
                            r"setConfigBits|mapDeviceMemory\w*|IOMemoryMap|"
                            r"IODMACommand|IOBufferMemoryDescriptor|IOInterruptEventSource|"
                            r"IOTimerEventSource|IOWorkLoop|evaluateObject|newUserClient|"
                            r"registerPowerDriver|PMinit|joinPMtree|setPowerState)\b")
        self.assertNotRegex(code, r"->(?:map|readBytes|writeBytes|read|write|open)\s*\(")

    def test_personality_requires_exact_device_and_observational_category(self):
        with (PACKAGE / "Info.plist").open("rb") as stream:
            info = plistlib.load(stream)
        self.assertEqual(info["CFBundleIdentifier"], "org.osx86.S540NvidiaPCIProbe")
        self.assertEqual(info["CFBundleVersion"], "0.1.0")
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
