#!/usr/bin/env bash
# Launch pymat from this checkout, with the sibling pydui on the path.
#
#   ./run.sh                 # desktop
#   ./run.sh --cli           # terminal session
#   ./run.sh examples/demo.py
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYDUI="${PYDUI:-$ROOT/../pydui}"
ENV_NAME="${PYMAT_ENV:-pymat}"

CONDA_BASE="$(conda info --base)"
# shellcheck disable=SC1091
source "$CONDA_BASE/etc/profile.d/conda.sh"
conda activate "$ENV_NAME"

export PYTHONPATH="$PYDUI/python:$ROOT${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONUNBUFFERED=1

exec python -m pymat "$@"
