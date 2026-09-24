#!/usr/bin/env bash
# Runs ONE real-runtime pytest target against a FRESH glsim process (glsim 0.29.2 can only
# load one contract per process without state pollution - see STAGE_2_5_REAL_WEB_VERIFICATION.md).
# Usage: scripts/run_real_web.sh <pytest-target> [extra glsim flags, e.g. nothing => --no-browser default]
set -u
TARGET="$1"; shift
GLSIM_FLAGS="${*:---no-browser}"
cd "$(dirname "$0")/.."
PID=$(netstat -ano | grep ":4000 .*LISTENING" | awk '{print $5}' | head -1)
[ -n "$PID" ] && taskkill //F //PID "$PID" >/dev/null 2>&1 && sleep 1
nohup python scripts/glsim_with_msg_value.py --port 4000 --validators 5 $GLSIM_FLAGS -v > .scratch/glsim_run.log 2>&1 &
for i in $(seq 1 20); do
  curl -s -m 2 http://127.0.0.1:4000/api -X POST -H "Content-Type: application/json" \
    -d '{"jsonrpc":"2.0","id":1,"method":"eth_chainId","params":[]}' | grep -q eec7 && break
  sleep 1
done
PYTHONIOENCODING=utf-8 python -m pytest "$TARGET" -s -q -p no:cacheprovider 2>&1 | grep -v "^INFO"
RC=${PIPESTATUS[0]}
PID=$(netstat -ano | grep ":4000 .*LISTENING" | awk '{print $5}' | head -1)
[ -n "$PID" ] && taskkill //F //PID "$PID" >/dev/null 2>&1
exit $RC
