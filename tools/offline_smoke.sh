#!/usr/bin/env bash
# Offline smoke test for one stage folder: build with no network, start with no network,
# answer a health request from inside the container, run the folder's tests inside it.
#
# Usage: tools/offline_smoke.sh <stage-folder> [port] [health-path] [mem-limit] [cpus]
# Example: tools/offline_smoke.sh stage-1 8080 /health 512m 1
#
# Exit code 0 only if build, start, health and tests all pass. Every step prints its own
# exit code; nothing is piped through a filter.
set -u
FOLDER="${1:?stage folder required}"
PORT="${2:-8080}"
HEALTH="${3:-/health}"
MEM="${4:-512m}"
CPUS="${5:-1}"
TAG="df-$(basename "$FOLDER" | tr '[:upper:]' '[:lower:]')-smoke"
NAME="${TAG}-run"
START_TIMEOUT="${START_TIMEOUT:-30}"

step() { printf '\n== %s\n' "$*"; }

step "1. offline build ($FOLDER -> $TAG)"
docker build --network none -t "$TAG" "$FOLDER"
rc=$?; echo "exit: $rc"; [ $rc -ne 0 ] && { echo "RESULT: FAIL (build needs network or is broken)"; exit 1; }

docker rm -f "$NAME" >/dev/null 2>&1
step "2. offline start (--network none, mem $MEM, cpus $CPUS)"
docker run -d --name "$NAME" --network none --memory "$MEM" --cpus "$CPUS" -e PORT="$PORT" "$TAG"
rc=$?; echo "exit: $rc"; [ $rc -ne 0 ] && { echo "RESULT: FAIL (container did not start)"; exit 1; }

step "3. health from inside the container (timeout ${START_TIMEOUT}s)"
t0=$(date +%s); ok=1
for i in $(seq 1 "$START_TIMEOUT"); do
  docker exec "$NAME" python3 -c "import urllib.request,sys; r=urllib.request.urlopen('http://127.0.0.1:${PORT}${HEALTH}', timeout=2); sys.exit(0 if r.status==200 else 1)" >/dev/null 2>&1
  if [ $? -eq 0 ]; then ok=0; break; fi
  sleep 1
done
t1=$(date +%s)
echo "exit: $ok  (start-to-healthy: $((t1-t0))s)"
if [ $ok -ne 0 ]; then
  echo "--- container logs"; docker logs "$NAME" 2>&1 | tail -n 40
  docker rm -f "$NAME" >/dev/null 2>&1
  echo "RESULT: FAIL (no healthy answer within ${START_TIMEOUT}s)"; exit 1
fi

step "4. tests inside the container"
docker exec "$NAME" sh -c 'cd /app && if [ -f run_tests.sh ]; then sh run_tests.sh; else python3 -m unittest discover -s tests -v; fi'
trc=$?; echo "exit: $trc"

step "5. peak memory"
docker stats --no-stream --format '{{.MemUsage}}' "$NAME"

docker rm -f "$NAME" >/dev/null 2>&1
if [ $trc -ne 0 ]; then echo "RESULT: FAIL (tests)"; exit 1; fi
echo "RESULT: PASS ($FOLDER builds offline, starts offline, healthy in $((t1-t0))s, tests exit 0)"
