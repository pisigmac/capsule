#!/usr/bin/env bash
# Publish Capsule clients.
#   npm:  capsule-ai, caps-ai, kapsule-ai
#   PyPI: caps-ai, capsule-ai, kapsule
# Local package.json / pyproject.toml names are restored on exit.
# A version that is already on the registry is skipped.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TS_DIR="${ROOT}/sdk/typescript"
PY_DIR="${ROOT}/sdk/python"

TS_NAMES=(capsule-ai caps-ai kapsule-ai)
PY_NAMES=(caps-ai capsule-ai kapsule)

if [[ -s "${HOME}/.nvm/nvm.sh" ]]; then
  # shellcheck disable=SC1091
  . "${HOME}/.nvm/nvm.sh"
  nvm use 22
fi

ts_canonical="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["name"])' "${TS_DIR}/package.json")"
py_canonical="$(python3 -c 'import re,sys; t=open(sys.argv[1]).read(); m=re.search(r"^name = \"([^\"]+)\"", t, re.M); print(m.group(1) if m else "")' "${PY_DIR}/pyproject.toml")"

if [[ -z "${py_canonical}" ]]; then
  echo "sdk/python/pyproject.toml is missing a project name" >&2
  exit 1
fi

set_ts_name() {
  python3 - "${TS_DIR}" "$1" <<'PY'
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
new = sys.argv[2]

pkg_path = root / "package.json"
pkg = json.loads(pkg_path.read_text())
old = pkg["name"]
pkg_path.write_text(pkg_path.read_text().replace(f'"name": "{old}"', f'"name": "{new}"', 1))

lock_path = root / "package-lock.json"
if lock_path.exists():
    lock = json.loads(lock_path.read_text())
    lock_old = lock.get("name", old)
    text = lock_path.read_text().replace(f'"name": "{lock_old}"', f'"name": "{new}"')
    lock_path.write_text(text)
PY
}

set_py_name() {
  python3 - "${PY_DIR}/pyproject.toml" "$1" <<'PY'
import re
import sys
from pathlib import Path

path = Path(sys.argv[1])
name = sys.argv[2]
text = path.read_text()
updated, count = re.subn(r'^name = "[^"]+"', f'name = "{name}"', text, count=1, flags=re.M)
if count != 1:
    raise SystemExit(f"could not set project name in {path}")
path.write_text(updated)
PY
}

restore_names() {
  set_ts_name "${ts_canonical}"
  set_py_name "${py_canonical}"
}
trap restore_names EXIT

pypi_has_version() {
  python3 - "$1" "$2" <<'PY'
import json
import sys
import urllib.error
import urllib.request

name, version = sys.argv[1], sys.argv[2]
url = f"https://pypi.org/pypi/{name}/json"
try:
    with urllib.request.urlopen(url, timeout=30) as response:
        data = json.load(response)
except urllib.error.HTTPError as exc:
    if exc.code == 404:
        print("missing")
        raise SystemExit(0)
    raise
print("exists" if version in (data.get("releases") or {}) else "missing")
PY
}

echo "==> TypeScript (${TS_NAMES[*]})"
cd "${TS_DIR}"
npm install
ts_version="$(python3 -c 'import json; print(json.load(open("package.json"))["version"])')"

for name in "${TS_NAMES[@]}"; do
  published="$(npm view "${name}" version 2>/dev/null || true)"
  published="${published//$'\n'/}"
  if [[ "${published}" == "${ts_version}" ]]; then
    echo "skip ${name}@${ts_version} (already on npm)"
    continue
  fi
  echo "publish ${name}@${ts_version}"
  set_ts_name "${name}"
  npm publish
done

echo "==> Python (${PY_NAMES[*]})"
cd "${PY_DIR}"
python3 -m pip install -q build twine
py_version="$(python3 -c 'import re; print(re.search(r"^version = \"([^\"]+)\"", open("pyproject.toml").read(), re.M).group(1))')"

for name in "${PY_NAMES[@]}"; do
  state="$(pypi_has_version "${name}" "${py_version}")"
  if [[ "${state}" == "exists" ]]; then
    echo "skip ${name}==${py_version} (already on PyPI)"
    continue
  fi
  if [[ "${name}" == "kapsule" ]]; then
    echo "note: PyPI kapsule ${py_version} is this thin client. pip install kapsule still resolves to the highest engine release."
  fi
  echo "publish ${name}==${py_version}"
  set_py_name "${name}"
  rm -rf dist
  python3 -m build
  twine upload dist/*
done

echo "==> Done"
