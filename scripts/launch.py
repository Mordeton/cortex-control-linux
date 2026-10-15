#!/usr/bin/env python3
"""Compatibility entry point; uses the installed app and maintained launcher."""
import sys
from desktop import main

if __name__ == '__main__':
    args = sys.argv[1:]
    connected = '--qc' in args
    args = [arg for arg in args if arg != '--qc']
    raise SystemExit(main(['run', *([] if connected else ['--disconnected']), *args]))
