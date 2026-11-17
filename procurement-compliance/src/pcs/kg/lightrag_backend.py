"""LightRAG（lightrag-hku）後端：以本機 Ollama 作為 LLM 與嵌入模型。

需安裝：pip install "lightrag-hku>=1.4"，並先 `ollama pull <PCS_LLM_MODEL>`、`ollama pull <PCS_EMBED_MODEL>`。
介面與 MiniGraphRAG 相同（query / get_document / find_quote / stats），讓 MCP Server 可無痛切換。
"""

from __future__ import annotations

import asyncio
from functools import partial

from ..config import settings
from ..corpus import Document


class LightRAGBackend:
    def __init__(self, docs: list[Document]):
        self.docs = {d.doc_id: d for d in docs}
        self._rag = None
        self._lock = asyncio.Lock()

    async def _ensure(self):
        async with self._lock:
            if self._rag is not None:
                return self._rag
            from lightrag import LightRAG
            from lightrag.kg.shared_storage import initialize_pipeline_status
            from lightrag.llm.ollama import ollama_embed, ollama_model_complete
            from lightrag.utils import EmbeddingFunc

            settings.lightrag_workdir.mkdir(parents=True, exist_ok=True)
            rag = LightRAG(
                working_dir=str(settings.lightrag_workdir),
                llm_model_func=ollama_model_complete,
                llm_model_name=settings.llm_model,
                llm_model_kwargs={"host": settings.ollama_host, "options": {"num_ctx": 32768}},
                embedding_func=EmbeddingFunc(
                    embedding_dim=settings.embed_dim,
                    max_token_size=8192,
                    func=partial(ollama_embed, embed_model=settings.embed_model, host=settings.ollama_host),
                ),
                addon_params={"language": "Traditional Chinese"},
            )
            await rag.initialize_storages()
            await initialize_pipeline_status()
            self._rag = rag
            return rag

    async def build(self) -> None:
        """建庫：將所有文件插入 LightRAG（實體/關係抽取由 LLM 完成，已插入者會被去重）。"""
        rag = await self._ensure()
        docs = list(self.docs.values())
        await rag.ainsert([d.text for d in docs], ids=[d.doc_id for d in docs],
                          file_paths=[d.path.name for d in docs])

    async def aquery(self, query: str, mode: str = "hybrid", top_k: int = 8) -> list[dict]:
        from lightrag import QueryParam

        rag = await self._ensure()
        ctx = await rag.aquery(query, param=QueryParam(mode=mode, top_k=top_k, only_need_context=True))
        # LightRAG 回傳組好的上下文字串；以單一 context 形式交給代理，並標註來源
        return [{"chunk_id": f"lightrag:{mode}", "doc_id": "*", "doc_title": "LightRAG context",
                 "rule_id": None, "text": str(ctx), "score": 1.0, "entities": []}]

    def query(self, query: str, mode: str = "hybrid", top_k: int = 8) -> list[dict]:
        return asyncio.run(self.aquery(query, mode, top_k))

    def get_document(self, doc_id: str) -> dict | None:
        d = self.docs.get(doc_id)
        return {"doc_id": d.doc_id, "title": d.title, "text": d.text} if d else None

    def find_quote(self, quote_no: str) -> dict | None:
        for d in self.docs.values():
            if quote_no in d.text and d.is_quote:
                return self.get_document(d.doc_id)
        return None

    def stats(self) -> dict:
        return {"documents": len(self.docs), "backend": "lightrag", "workdir": str(settings.lightrag_workdir)}

    def relations(self) -> list[dict]:
        return []
