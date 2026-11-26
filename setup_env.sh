#!/usr/bin/env bash
# Create (or repair) the `pymat` conda environment.
#
#   ./setup_env.sh
#
# It creates the environment, installs numpy/matplotlib, puts the sibling pydui
# checkout on sys.path, and installs pymat itself in editable mode.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYDUI="${PYDUI:-$ROOT/../pydui}"
ENV_NAME="${PYMAT_ENV:-pymat}"

if [[ ! -d "$PYDUI/python/dui" ]]; then
  echo "pydui not found at $PYDUI (set PYDUI=/path/to/pydui)" >&2
  exit 1
fi

CONDA_BASE="$(conda info --base)"
# shellcheck disable=SC1091
source "$CONDA_BASE/etc/profile.d/conda.sh"

if ! conda env list | awk '{print $1}' | grep -qx "$ENV_NAME"; then
  conda create -n "$ENV_NAME" python=3.14 -y
fi
conda activate "$ENV_NAME"

python -m pip install -q --upgrade pip
python -m pip install -q --only-binary=:all: numpy pandas scipy matplotlib
python -m pip install -q -e "$ROOT"

SITE="$(python -c 'import site; print(site.getsitepackages()[0])')"
printf '%s\n' "$PYDUI/python" > "$SITE/pydui-local.pth"

python - <<'PY'
import dui, pymat
print("dui     :", dui.__file__)
print("pymat   :", pymat.__file__, pymat.__version__)
PY

echo
echo "Ready.  Activate with:  conda activate $ENV_NAME"
echo "Run the desktop with:   ./run.sh"
