#!/bin/sh
# Compatibility entry point; all launches use the maintained desktop launcher.
set -eu
cd -- "$(dirname -- "$0")"
exec ./cortex-control run "$@"
