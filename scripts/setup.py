#!/usr/bin/env python3
"""Compatibility entry point for the unified installer."""
import sys
from desktop import main

if __name__ == '__main__':
    raise SystemExit(main(['install', *sys.argv[1:]]))
