"""
RAG 检索器 - 结合向量搜索 + 权限过滤 + 文件级兜底

检索策略：
1. 先用向量搜 top_k 个最相关的 chunk（精准片段）
2. 收集这些 chunk 所属的 document 列表
3. 把这些 document 的完整内容也返回（带 关联片段 标注）
4. Prompt 里 LLM 既能看精准片段，也能看完整文件上下文
"""
from typing import List, Dict, Optional
from app.rag.embeddings import embedding_manager
from app.rag.vector_store import faiss_store
from app.core.logging import get_logger

logger = get_logger()


class RAGRetriever:
    """RAG 检索器"""

    def __init__(self, top_k: int = 12, score_threshold: float = 0.0):
        # score_threshold 从 0.3 降到 0.0 —— Mock embedding 是随机向量，
        # 分数分布没有意义，应该多捞一点让 LLM 自己筛选
        self.top_k = top_k
        self.score_threshold = score_threshold

    def retrieve(
        self,
        query: str,
        allowed_repo_ids: Optional[List[int]] = None,
        top_k: Optional[int] = None,
    ) -> List[Dict]:
        """
        检索相关代码片段 + 文件级兜底

        Returns:
            返回结构统一的 source 列表，每个 item 要么是 chunk（精准命中），
            要么是 document（文件级兜底）。LLM 拿到后自然知道什么时候看片段、什么时候看全貌。
        """
        # 生成查询向量
        query_vector = embedding_manager.get_single_embedding(query)
        if query_vector.size == 0:
            return []

        # ===== Step 1: 向量搜 top_k chunks =====
        hits = faiss_store.search(
            query_vector=query_vector,
            top_k=top_k or self.top_k,
            allowed_repo_ids=allowed_repo_ids,
            score_threshold=self.score_threshold,
        )

        if not hits:
            return []

        # ===== Step 2: 收集命中的 document_id =====
        doc_ids_seen = {}  # doc_id -> best_chunk_score
        chunk_results = []

        for hit in hits:
            content = hit.get("content", "")
            if not content:
                continue

            doc_id = hit.get("document_id")
            score = hit.get("score", 0)
            if doc_id and doc_id not in doc_ids_seen:
                doc_ids_seen[doc_id] = score

            if len(content) > 8000:
                content = content[:8000] + "\n# ... (片段已截断)"

            chunk_results.append({
                "type": "chunk",
                "repo_id": hit.get("repo_id"),
                "document_id": doc_id,
                "file_path": hit.get("file_path"),
                "chunk_type": hit.get("chunk_type", "text"),
                "chunk_name": hit.get("chunk_name"),
                "start_line": hit.get("start_line"),
                "end_line": hit.get("end_line"),
                "content": content,
                "score": round(score, 4),
            })

        # ===== Step 3: 文件级兜底 =====
        # 把 top 3 个命中 document 的完整内容也捞出来，
        # 让 LLM 不只是看到碎片而是看到文件全貌
        doc_results = self._load_documents_sync(list(doc_ids_seen.keys())[:3])

        # ===== Step 4: 合并返回 =====
        # chunk 按分数排序放前面（精准命中），documents 放后面（完整上下文）
        chunk_results.sort(key=lambda x: x["score"], reverse=True)
        all_results = chunk_results + doc_results

        logger.info(
            f"检索完成: query='{query[:50]}...', "
            f"chunks={len(chunk_results)}, docs={len(doc_results)}, total={len(all_results)}"
        )
        return all_results

    def _load_documents_sync(self, doc_ids: List[int]) -> List[Dict]:
        """同步加载 document 完整内容（内部起新 event loop 线程）"""
        if not doc_ids:
            return []

        import asyncio
        import concurrent.futures
        from app.db.database import async_session_factory
        from sqlalchemy import select
        from app.models.document import Document

        async def _load():
            results = []
            try:
                async with async_session_factory() as db:
                    r = await db.execute(
                        select(Document).where(Document.id.in_(doc_ids))
                    )
                    for doc in r.scalars().all():
                        content = doc.content or ""
                        if content and len(content) > 20000:
                            content = content[:20000] + "\n# ... (文件过长已截断，仅保留前 20000 字符)"
                        results.append({
                            "type": "document",
                            "repo_id": doc.repo_id,
                            "document_id": doc.id,
                            "file_path": doc.file_path,
                            "chunk_type": "document",
                            "chunk_name": None,
                            "start_line": 1,
                            "end_line": doc.line_count or content.count("\n") + 1,
                            "content": content,
                            "score": 0.0,
                        })
            except Exception as e:
                logger.warning(f"加载 document 完整内容失败: {e}")
            return results

        # 总是在独立线程里起新 event loop，不依赖调用方的 loop 状态
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(asyncio.run, _load())
                return future.result(timeout=15)
        except Exception as e:
            logger.warning(f"_load_documents_sync 失败: {e}")
            return []


# 全局实例
retriever = RAGRetriever()
