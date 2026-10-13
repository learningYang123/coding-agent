"""
向量存储 - 基于 FAISS 实现
支持按仓库隔离索引，实现权限过滤
"""
import os
import json
from typing import List, Dict, Optional, Tuple
from pathlib import Path
import numpy as np
import faiss

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger()


class FAISSStore:
    """
    FAISS 向量存储

    设计：
    - 主索引存储所有向量
    - 元数据存储在 JSON 文件中：vector_id -> {repo_id, chunk_id, content, ...}
    - 搜索时先过滤 repo_ids 白名单，再做向量检索
    """

    def __init__(self):
        self.index_path = Path(settings.FAISS_INDEX_PATH)
        self.index_path.mkdir(parents=True, exist_ok=True)

        self.index_file = self.index_path / "index.faiss"
        self.metadata_file = self.index_path / "metadata.json"

        self.dimension = settings.embedding_dimension
        self.index: Optional[faiss.IndexFlatIP] = None
        self.metadata: Dict[str, Dict] = {}  # vector_id -> metadata
        self._next_id = 0

        self._load_or_create()

    def _load_or_create(self):
        """加载或创建索引"""
        if self.index_file.exists() and self.metadata_file.exists():
            try:
                self.index = faiss.read_index(str(self.index_file))
                with open(self.metadata_file, "r", encoding="utf-8") as f:
                    self.metadata = json.load(f)
                # 计算下一个 ID
                if self.metadata:
                    self._next_id = max(int(k) for k in self.metadata.keys()) + 1
                logger.info(f"加载已有 FAISS 索引: {self.index.ntotal} 条向量")
            except Exception as e:
                logger.warning(f"加载 FAISS 索引失败，重新创建: {e}")
                self._create_new_index()
        else:
            self._create_new_index()

    def _create_new_index(self):
        """创建新索引"""
        self.index = faiss.IndexFlatIP(self.dimension)  # 内积（cosine，因为已归一化）
        self.metadata = {}
        self._next_id = 0
        logger.info(f"创建新 FAISS 索引，维度={self.dimension}")

    def save(self):
        """持久化索引"""
        faiss.write_index(self.index, str(self.index_file))
        with open(self.metadata_file, "w", encoding="utf-8") as f:
            json.dump(self.metadata, f, ensure_ascii=False, indent=2)
        logger.info(f"FAISS 索引已保存: {self.index.ntotal} 条")

    def add_vectors(
        self,
        vectors: np.ndarray,
        metadatas: List[Dict],
    ) -> List[str]:
        """
        添加向量到索引

        Args:
            vectors: numpy 数组 (n, dimension)
            metadatas: 每条向量对应的元数据列表

        Returns:
            生成的 vector_id 列表
        """
        if len(vectors) == 0:
            return []

        # 确保是 float32
        vectors = vectors.astype(np.float32)

        # 生成 ID
        ids = []
        for i in range(len(vectors)):
            vid = str(self._next_id)
            self._next_id += 1
            ids.append(vid)
            self.metadata[vid] = metadatas[i] if i < len(metadatas) else {}

        # 添加到 FAISS
        self.index.add(vectors)

        # 保存
        self.save()

        return ids

    def search(
        self,
        query_vector: np.ndarray,
        top_k: int = 10,
        allowed_repo_ids: Optional[List[int]] = None,
        score_threshold: float = 0.0,
    ) -> List[Dict]:
        """
        向量检索

        Args:
            query_vector: 查询向量
            top_k: 返回数量
            allowed_repo_ids: 允许的仓库 ID 列表（权限过滤），None 表示全部
            score_threshold: 分数阈值（0-1）

        Returns:
            命中的元数据列表，按分数降序，包含 score 字段
        """
        if self.index.ntotal == 0:
            return []

        query_vector = query_vector.astype(np.float32).reshape(1, -1)

        # 如果没有权限过滤，直接搜索
        if allowed_repo_ids is None:
            k = min(top_k, self.index.ntotal)
            scores, indices = self.index.search(query_vector, k)

            results = []
            for i, idx in enumerate(indices[0]):
                if idx == -1:
                    continue
                vid = str(idx)
                if vid in self.metadata:
                    result = self.metadata[vid].copy()
                    result["score"] = float(scores[0][i])
                    result["vector_id"] = vid
                    if result["score"] >= score_threshold:
                        results.append(result)
            return results

        # 有权限过滤：先搜索更多，再过滤
        # 因为 FAISS 不支持预过滤，我们搜索更大的 k 然后过滤
        search_k = min(top_k * 10, self.index.ntotal)
        scores, indices = self.index.search(query_vector, search_k)

        allowed_set = set(allowed_repo_ids)
        results = []
        for i, idx in enumerate(indices[0]):
            if idx == -1:
                continue
            vid = str(idx)
            if vid in self.metadata:
                meta = self.metadata[vid]
                repo_id = meta.get("repo_id")
                if repo_id is not None and repo_id in allowed_set:
                    result = meta.copy()
                    result["score"] = float(scores[0][i])
                    result["vector_id"] = vid
                    if result["score"] >= score_threshold:
                        results.append(result)

        # 如果过滤后不够，再扩大搜索范围
        if len(results) < top_k and search_k < self.index.ntotal:
            search_k = min(self.index.ntotal, search_k * 5)
            scores, indices = self.index.search(query_vector, search_k)
            seen = {r["vector_id"] for r in results}
            for i, idx in enumerate(indices[0]):
                if idx == -1:
                    continue
                vid = str(idx)
                if vid in seen:
                    continue
                if vid in self.metadata:
                    meta = self.metadata[vid]
                    repo_id = meta.get("repo_id")
                    if repo_id is not None and repo_id in allowed_set:
                        result = meta.copy()
                        result["score"] = float(scores[0][i])
                        result["vector_id"] = vid
                        if result["score"] >= score_threshold:
                            results.append(result)
                            if len(results) >= top_k:
                                break

        # 按分数降序，取 top_k
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]

    def delete_by_repo(self, repo_id: int):
        """删除指定仓库的所有向量"""
        # FAISS 不支持按 ID 删除，需要重建索引
        # 找出要保留的向量
        keep_ids = []
        keep_vectors = []
        keep_metadatas = []

        all_ids = list(self.metadata.keys())
        for vid in all_ids:
            if self.metadata[vid].get("repo_id") != repo_id:
                keep_ids.append(vid)
                keep_metadatas.append(self.metadata[vid])

        if len(keep_ids) == len(self.metadata):
            logger.info(f"仓库 {repo_id} 没有向量，跳过删除")
            return

        # 重新构建索引
        new_index = faiss.IndexFlatIP(self.dimension)
        new_metadata = {}

        # 保留的向量需要重新提取
        if keep_ids:
            # 从旧索引中提取保留的向量
            keep_vectors = np.zeros((len(keep_ids), self.dimension), dtype=np.float32)
            for i, vid in enumerate(keep_ids):
                old_idx = int(vid)
                if old_idx < self.index.ntotal:
                    vec = self.index.reconstruct(old_idx)
                    keep_vectors[i] = vec

            new_index.add(keep_vectors)

        # 重新分配连续 ID
        for i, vid in enumerate(keep_ids):
            new_metadata[str(i)] = keep_metadatas[i]

        self.index = new_index
        self.metadata = new_metadata
        self._next_id = len(new_metadata)

        self.save()
        logger.info(f"已删除仓库 {repo_id} 的向量，剩余 {self.index.ntotal} 条")

    def get_stats(self) -> Dict:
        """获取索引统计"""
        repo_ids = set()
        for meta in self.metadata.values():
            rid = meta.get("repo_id")
            if rid is not None:
                repo_ids.add(rid)

        return {
            "total_vectors": self.index.ntotal,
            "total_repos": len(repo_ids),
            "dimension": self.dimension,
        }


# 全局实例
faiss_store = FAISSStore()
