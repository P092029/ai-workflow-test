"""集中管理環境變數設定。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    corpus_dir: Path = Path(os.getenv("PCS_CORPUS_DIR", PROJECT_ROOT / "data" / "corpus"))
    testset_path: Path = Path(os.getenv("PCS_TESTSET", PROJECT_ROOT / "data" / "testset" / "cases.jsonl"))
    results_dir: Path = Path(os.getenv("PCS_RESULTS_DIR", PROJECT_ROOT / "results"))

    # 知識圖譜後端：mini（內建輕量圖譜，離線可跑）或 lightrag（lightrag-hku + Ollama）
    kg_backend: str = os.getenv("PCS_KG_BACKEND", "mini")
    lightrag_workdir: Path = Path(os.getenv("PCS_LIGHTRAG_WORKDIR", PROJECT_ROOT / "rag_storage"))

    # 推理器：rule（確定性規則推理，用於管線驗證）或 llm（透過 Ollama 呼叫本機 LLM）
    reasoner: str = os.getenv("PCS_REASONER", "rule")

    ollama_host: str = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    llm_model: str = os.getenv("PCS_LLM_MODEL", "qwen2.5:7b-instruct")
    embed_model: str = os.getenv("PCS_EMBED_MODEL", "bge-m3")
    embed_dim: int = int(os.getenv("PCS_EMBED_DIM", "1024"))

    # 服務位址（Docker Compose 內以服務名稱連線）
    mcp_url: str | None = os.getenv("PCS_MCP_URL")  # 例：http://kg-mcp:8100/mcp
    legal_url: str = os.getenv("PCS_LEGAL_URL", "http://localhost:8201")
    finance_url: str = os.getenv("PCS_FINANCE_URL", "http://localhost:8202")


settings = Settings()
