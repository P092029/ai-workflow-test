#!/usr/bin/env bash
# 下載 LLM 與嵌入模型到「容器版」Ollama（只有使用 --profile docker-ollama 時需要）
# 使用電腦上的 Ollama 時，直接執行 ollama pull 即可
set -euo pipefail
LLM=${PCS_LLM_MODEL:-qwen2.5:7b-instruct}
EMB=${PCS_EMBED_MODEL:-bge-m3}
docker compose exec ollama ollama pull "$LLM"
docker compose exec ollama ollama pull "$EMB"
docker compose exec ollama ollama list
