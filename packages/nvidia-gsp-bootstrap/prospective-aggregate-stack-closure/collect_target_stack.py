#!/usr/bin/env python3
"""Read actual target kernel stack capacity without loading or configuring code."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys


def collect():
    if sys.platform != 'darwin' or platform.machine() != 'x86_64':
        raise ValueError('The target stack witness requires the actual Intel macOS host')
    executable = Path('/usr/sbin/sysctl').resolve(strict=True)
    raw = subprocess.check_output([str(executable), '-b', 'kern.stack_size'])
    if len(raw) not in (4, 8):
        raise ValueError('kern.stack_size did not return one actual 32/64-bit integer')
    capacity = int.from_bytes(raw, 'little')
    if not 4096 <= capacity <= 1024 * 1024 or capacity % 4096:
        raise ValueError('Actual kern.stack_size is not a plausible aligned capacity')
    build = subprocess.check_output([str(executable), '-n', 'kern.osversion'], text=True).strip()
    return {'format': 1, 'scope': 'read-only-actual-target-kernel-stack-capacity',
        'architecture': platform.machine(), 'darwin_release': platform.release(),
        'build': build, 'expected_target_build': '25G241', 'expected_target_build_observed': build == '25G241',
        'sysctl_name': 'kern.stack_size', 'raw_hex': raw.hex(), 'raw_width_bytes': len(raw),
        'actual_kernel_stack_capacity_bytes': capacity, 'capacity_observed': True,
        'physical_irq_stack_capacity_observed': False,
        'physical_irq_experimental_assumption_bytes': 16384,
        'sysctl_executable_sha256': hashlib.sha256(executable.read_bytes()).hexdigest(),
        'stack_depth_high_water_used_as_capacity': False,
        'module_loaded': False, 'system_security_changed': False,
        'formal_stack_bound_proven': False, 'original_entry_admission': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = collect()
    text = json.dumps(result, indent=2, sort_keys=True) + '\n'
    if args.output:
        with args.output.open('x') as stream:
            stream.write(text)
    else:
        print(text, end='')
