#!/usr/bin/env python3
"""Launcher so the plugin works from its root without installing a package."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from worddrill.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
