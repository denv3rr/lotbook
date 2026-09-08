#!/usr/bin/env bash
set -euo pipefail
python "$(cd "$(dirname "$0")" && pwd)/clear_bootstrap.py" "$@"
