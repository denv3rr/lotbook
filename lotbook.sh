#!/usr/bin/env bash
set -euo pipefail
python "$(cd "$(dirname "$0")" && pwd)/lotbook_bootstrap.py" "$@"
