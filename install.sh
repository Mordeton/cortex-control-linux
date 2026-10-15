#!/bin/sh
set -eu
cd -- "$(dirname -- "$0")"
exec ./cortex-control install "$@"
