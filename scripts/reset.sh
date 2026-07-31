#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export UV_CACHE_DIR="${UV_CACHE_DIR:-/private/tmp/uv-cache}"

if [[ $# -eq 0 ]]; then
  set -- --all
fi

cd "$ROOT_DIR/backend"
exec env -u VIRTUAL_ENV uv run python -m demo.reset "$@"
