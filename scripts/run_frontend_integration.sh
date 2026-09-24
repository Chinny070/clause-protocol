#!/usr/bin/env bash
# Runs the frontend adapter integration test against a FRESH local glsim (one contract per process).
# Leaves the simulator RUNNING afterwards when KEEP_GLSIM=1 (used for the local visual check); the deployed
# contract address is written to .scratch/local_address.txt. Local simulator only: no StudioNet, no user wallet/key.
set -u
cd "$(dirname "$0")/.."
PID=$(netstat -ano | grep ":4000 .*LISTENING" | awk '{print $5}' | head -1)
[ -n "$PID" ] && taskkill //F //PID "$PID" >/dev/null 2>&1 && sleep 1
nohup python scripts/glsim_with_msg_value.py --port 4000 --validators 5 --no-browser -v > .scratch/glsim_fe.log 2>&1 &
for i in $(seq 1 20); do
  curl -s -m 2 http://127.0.0.1:4000/api -X POST -H "Content-Type: application/json" \
    -d '{"jsonrpc":"2.0","id":1,"method":"eth_chainId","params":[]}' | grep -q eec7 && break
  sleep 1
done
(cd frontend && npx vitest run --config vitest.integration.config.ts 2>&1 | grep -vE "^\s*$")
RC=${PIPESTATUS[0]}
if [ "${KEEP_GLSIM:-0}" != "1" ]; then
  PID=$(netstat -ano | grep ":4000 .*LISTENING" | awk '{print $5}' | head -1)
  [ -n "$PID" ] && taskkill //F //PID "$PID" >/dev/null 2>&1
fi
exit $RC
