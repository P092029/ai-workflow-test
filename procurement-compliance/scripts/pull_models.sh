#!/usr/bin/env bash
# 下載 LLM 與嵌入模型到 Ollama 容器（第 1–2 週）
set -euo pipefail
LLM=${PCS_LLM_MODEL:-qwen2.5:7b-instruct}
EMB=${PCS_EMBED_MODEL:-bge-m3}
docker compose exec ollama ollama pull "$LLM"
docker compose exec ollama ollama pull "$EMB"
docker compose exec ollama ollama list
