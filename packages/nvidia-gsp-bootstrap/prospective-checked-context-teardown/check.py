#!/usr/bin/env python3
from pathlib import Path
import importlib.util
HERE = Path(__file__).resolve().parent
path = HERE.parent / 'prospective-dma-stop-closure/control_common.py'
spec = importlib.util.spec_from_file_location('s540_context_controls', path)
module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
if __name__ == '__main__': module.main(HERE, 'context')
