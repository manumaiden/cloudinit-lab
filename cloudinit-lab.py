#!/usr/bin/env python3
"""Entry point shim — symlinked into ~/bin by install.sh."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cloudinit_lab.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
