#!/usr/bin/env python
"""Runner script for Social Media Monitoring CLI."""

import sys

# Force UTF-8 encoding for standard output/error on Windows
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

from app.cli import main

if __name__ == "__main__":
    main()
