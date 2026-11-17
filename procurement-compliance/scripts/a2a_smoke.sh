#!/usr/bin/env bash
# 以 curl 走一次 A2A 協定：取 Agent Card → message/send → tasks/get 輪詢
set -euo pipefail
URL=${1:-http://localhost:8200}
Q=${2:-報價單 Q-2025-0601 能否不經公開招標，直接向廠商採購？}
curl -s "$URL/.well-known/agent-card.json" | python3 -m json.tool | head -20
TASK=$(curl -s "$URL/" -H 'content-type: application/json' -d "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"message/send\",\"params\":{\"message\":{\"role\":\"user\",\"kind\":\"message\",\"messageId\":\"m1\",\"parts\":[{\"kind\":\"data\",\"data\":{\"question\":\"$Q\"}}]}}}" | python3 -c 'import sys,json;print(json.load(sys.stdin)["result"]["id"])')
echo "task: $TASK"
while :; do
  R=$(curl -s "$URL/" -H 'content-type: application/json' -d "{\"jsonrpc\":\"2.0\",\"id\":2,\"method\":\"tasks/get\",\"params\":{\"id\":\"$TASK\"}}")
  S=$(echo "$R" | python3 -c 'import sys,json;print(json.load(sys.stdin)["result"]["status"]["state"])')
  echo "state: $S"
  [[ "$S" == completed || "$S" == failed ]] && break
  sleep 2
done
echo "$R" | python3 -m json.tool
