#!/usr/bin/env bash
# Live HTTP checks against the Capsule API (create, dedup, search, compose, 409, delete).
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DIR"

BASE="${CAPSULE_E2E_URL:-}"
KEEP_SERVER=0
WORKDIR="${CAPSULE_E2E_DIR:-}"
SERVER_PID=""
PASS=0
FAIL=0

usage() {
  cat <<'EOF'
Usage: scripts/e2e_curl.sh [--url URL] [--keep]

  --url URL   Hit an already-running API (default: start an isolated one)
  --keep      Leave the isolated API running after the run

Env: CAPSULE_E2E_URL, CAPSULE_E2E_DIR, CAPSULE_E2E_PORT (default 19100)
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --url)
      BASE="${2:?}"
      shift 2
      ;;
    --keep)
      KEEP_SERVER=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

API=""
WORKDIR="${WORKDIR:-$(mktemp -d /tmp/capsule-e2e-XXXXXX)}"

cleanup() {
  if [[ -n "$SERVER_PID" && "$KEEP_SERVER" -eq 0 ]]; then
    kill "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

json_field() {
  python3 -c "import json,sys; print(json.load(sys.stdin)$1)"
}

req() {
  local method="$1"
  local path="$2"
  local body="${3:-}"
  local tmp
  tmp="$(mktemp)"
  local args=(-sS --noproxy '*' -D "$tmp.hdr" -o "$tmp.body" -w "%{http_code}" -X "$method")
  if [[ -n "$body" ]]; then
    args+=(-H "Content-Type: application/json" -d "$body")
  fi
  local code
  code="$(curl "${args[@]}" "${API}${path}")"
  echo "$code" >"$tmp.code"
  echo "$tmp"
}

expect() {
  local name="$1"
  local tmp="$2"
  local want="$3"
  local code
  code="$(cat "$tmp.code")"
  if [[ "$code" == "$want" ]]; then
    echo "PASS  $name  HTTP $code"
    PASS=$((PASS + 1))
  else
    echo "FAIL  $name  expected HTTP $want, got $code"
    echo "      $(tr -d '\n' <"$tmp.body" | head -c 240)"
    FAIL=$((FAIL + 1))
  fi
}

start_isolated() {
  local port="${CAPSULE_E2E_PORT:-19100}"
  BASE="http://127.0.0.1:${port}"
  mkdir -p "$WORKDIR/capsules"
  local uvicorn=".venv/bin/uvicorn"
  if [[ ! -x "$uvicorn" ]]; then
    uvicorn="uvicorn"
  fi
  echo "Starting isolated API on $BASE (dir $WORKDIR)"
  CAPSULES_DIR="$WORKDIR/capsules" \
    CAPSULE_DATABASE_URL="sqlite:///${WORKDIR}/capsule.db" \
    CAPSULE_WATCH=false \
    CAPSULE_GIT_COMMIT=false \
    CAPSULE_EMBED=false \
    "$uvicorn" services.api.main:app --host 127.0.0.1 --port "$port" --workers 1 \
    >/tmp/capsule-e2e-server.log 2>&1 &
  SERVER_PID=$!
  local i
  for i in $(seq 1 40); do
    if curl -fsS --noproxy '*' "$BASE/health" >/dev/null 2>&1; then
      return 0
    fi
    if ! kill -0 "$SERVER_PID" 2>/dev/null; then
      echo "API exited during startup. Log:" >&2
      cat /tmp/capsule-e2e-server.log >&2 || true
      exit 1
    fi
    sleep 0.25
  done
  echo "API did not become healthy at $BASE" >&2
  cat /tmp/capsule-e2e-server.log >&2 || true
  exit 1
}

if [[ -z "$BASE" ]]; then
  start_isolated
else
  echo "Using running API at $BASE"
fi
API="${BASE%/}/api/v1"

code="$(curl -sS --noproxy '*' -o "$WORKDIR/health.json" -w "%{http_code}" "$BASE/health")"
echo "$code" >"$WORKDIR/health.code"
if [[ "$code" == "200" ]]; then
  echo "PASS  health  HTTP 200"
  PASS=$((PASS + 1))
else
  echo "FAIL  health  expected HTTP 200, got $code"
  FAIL=$((FAIL + 1))
fi

create_a="$(req POST /capsules '{"topic":"E2E JWT bypass","content":"Staging skips JWT when X-Debug-Override is set for mobile CI.","tags":["auth","e2e"],"confidence":"high","source":"curl-e2e"}')"
expect "create A" "$create_a" 201
ID_A="$(json_field "['id']" <"$create_a.body")"

dedup="$(req POST /capsules '{"topic":"Different title same fact","content":"Staging skips JWT when X-Debug-Override is set for mobile CI.","tags":["ops"],"confidence":"medium"}')"
expect "dedup same body" "$dedup" 200
DEDUPED="$(json_field "['deduped']" <"$dedup.body")"
DEDUP_ID="$(json_field "['id']" <"$dedup.body")"
if [[ "$DEDUPED" == "True" || "$DEDUPED" == "true" ]] && [[ "$DEDUP_ID" == "$ID_A" ]]; then
  echo "PASS  dedup same id + merged tags"
  PASS=$((PASS + 1))
else
  echo "FAIL  dedup same id + merged tags  (deduped=$DEDUPED id=$DEDUP_ID expected=$ID_A)"
  FAIL=$((FAIL + 1))
fi

create_b="$(req POST /capsules '{"topic":"E2E connection pool","content":"Postgres pool maxes out at 100 connections under load.","tags":["database"],"confidence":"medium"}')"
expect "create B" "$create_b" 201
ID_B="$(json_field "['id']" <"$create_b.body")"

expect "get A" "$(req GET "/capsules/${ID_A}")" 200
expect "list" "$(req GET "/capsules?limit=10")" 200

search="$(req POST /search '{"query":"JWT","tags":["auth"]}')"
expect "search JWT+auth" "$search" 200
SEARCH_N="$(python3 -c "import json; print(len(json.load(open('$search.body'))))")"
if [[ "$SEARCH_N" == "1" ]]; then
  echo "PASS  search returned 1 row"
  PASS=$((PASS + 1))
else
  echo "FAIL  search returned $SEARCH_N rows (want 1)"
  FAIL=$((FAIL + 1))
fi

compose="$(req POST /compose '{"query":"staging","max_tokens":500}')"
expect "compose" "$compose" 200
COUNT="$(json_field "['capsule_count']" <"$compose.body")"
if [[ "$COUNT" == "1" ]]; then
  echo "PASS  compose included 1 capsule"
  PASS=$((PASS + 1))
else
  echo "FAIL  compose capsule_count=$COUNT (want 1)"
  FAIL=$((FAIL + 1))
fi

expect "patch B confidence" "$(req PATCH "/capsules/${ID_B}" '{"confidence":"high"}')" 200
expect "patch B into A body" "$(req PATCH "/capsules/${ID_B}" '{"content":"Staging skips JWT when X-Debug-Override is set for mobile CI."}')" 409
expect "link A->B" "$(req POST /relationships "{\"from_capsule_id\":\"${ID_A}\",\"to_capsule_id\":\"${ID_B}\",\"relationship_type\":\"relates_to\"}")" 201
expect "relationships" "$(req GET "/capsules/${ID_A}/relationships")" 200
expect "tags" "$(req GET /tags)" 200
expect "status" "$(req GET /status)" 200
expect "archive B" "$(req POST "/capsules/${ID_B}/archive")" 200
expect "stale" "$(req GET "/stale?days=1")" 200
expect "delete B" "$(req DELETE "/capsules/${ID_B}")" 204
expect "get deleted B" "$(req GET "/capsules/${ID_B}")" 404
expect "sync" "$(req POST /sync)" 200

echo
echo "Result: $PASS passed, $FAIL failed  ($BASE)"
if [[ "$KEEP_SERVER" -eq 1 && -n "$SERVER_PID" ]]; then
  echo "API left running pid=$SERVER_PID  $BASE  dir=$WORKDIR"
  trap - EXIT
fi
[[ "$FAIL" -eq 0 ]]
