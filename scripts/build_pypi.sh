#!/usr/bin/env bash
# Build sdist + wheel for each PyPI name (korn and pykorn).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

OUT="${1:-dist}"
NAMES=(korn pykorn)

python3 - <<'PY'
from pathlib import Path
import re
text = Path("pyproject.toml").read_text()
match = re.search(r'^name = "([^"]+)"', text, re.M)
if not match:
    raise SystemExit("pyproject.toml is missing project name")
Path(".pypi-canonical-name").write_text(match.group(1))
PY

CANONICAL="$(cat .pypi-canonical-name)"
rm -f .pypi-canonical-name

restore_name() {
  python3 -c "
from pathlib import Path
import re
p = Path('pyproject.toml')
p.write_text(re.sub(r'^name = \"[^\"]+\"', 'name = \"${CANONICAL}\"', p.read_text(), count=1, flags=re.M))
"
}
trap restore_name EXIT

python3 -m pip install -q build setuptools wheel
rm -rf "${OUT}"

for name in "${NAMES[@]}"; do
  python3 -c "
from pathlib import Path
import re
p = Path('pyproject.toml')
p.write_text(re.sub(r'^name = \"[^\"]+\"', 'name = \"${name}\"', p.read_text(), count=1, flags=re.M))
"
  python3 -m build --no-isolation --outdir "${OUT}/${name}"
done

echo "Built:"
find "${OUT}" -type f -print
