"""
Embedding 模型管理器
支持本地 sentence-transformers 和在线 API（DeepSeek）
"""
from typing import List
import numpy as np
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger()


class EmbeddingManager:
    """Embedding 管理器"""

    def __init__(self):
        self._model = None
        self._initialized = False
        self._init_model()

    def _init_model(self):
        """初始化 Embedding 模型"""
        try:
            if settings.EMBEDDING_PROVIDER == "local":
                self._init_local_model()
            elif settings.EMBEDDING_PROVIDER == "deepseek":
                self._init_deepseek_client()
            else:
                raise ValueError(f"不支持的 Embedding Provider: {settings.EMBEDDING_PROVIDER}")
            self._initialized = True
            logger.info(f"Embedding 模型初始化成功: {settings.EMBEDDING_PROVIDER}")
        except Exception as e:
            logger.error(f"Embedding 模型初始化失败: {e}")
            # 回退到 mock 模式，返回随机向量
            self._initialized = False
            logger.warning("将使用 Mock Embedding（随机向量），仅用于开发测试")

    def _init_local_model(self):
        """初始化本地 sentence-transformers 模型"""
        from sentence_transformers import SentenceTransformer

        model_path = settings.EMBEDDING_MODEL_PATH
        try:
            self._model = SentenceTransformer(model_path)
        except Exception:
            # 如果本地没有，自动下载
            logger.info(f"本地模型不存在，尝试下载 all-MiniLM-L6-v2")
            self._model = SentenceTransformer("all-MiniLM-L6-v2")
            # 保存到指定路径
            import os
            os.makedirs(model_path, exist_ok=True)
            self._model.save(model_path)

    def _init_deepseek_client(self):
        """初始化 DeepSeek Embedding 客户端"""
        import httpx

        self._client = httpx.Client(timeout=30.0)
        self._api_key = settings.EMBEDDING_API_KEY or settings.LLM_API_KEY
        self._base_url = settings.LLM_BASE_URL
        self._model_name = settings.EMBEDDING_MODEL

    def get_embeddings(self, texts: List[str]) -> np.ndarray:
        """
        获取文本列表的向量表示

        Args:
            texts: 文本列表

        Returns:
            numpy 数组，shape = (len(texts), dimension)
        """
        if not texts:
            return np.array([])

        if self._initialized and settings.EMBEDDING_PROVIDER == "local":
            return self._model.encode(texts, normalize_embeddings=True)
        elif self._initialized and settings.EMBEDDING_PROVIDER == "deepseek":
            return self._get_deepseek_embeddings(texts)
        else:
            # Mock 模式：返回随机向量
            dim = settings.embedding_dimension
            logger.warning(f"使用 Mock Embedding，生成 {len(texts)} 个 {dim} 维随机向量")
            return np.random.randn(len(texts), dim).astype(np.float32)

    def get_single_embedding(self, text: str) -> np.ndarray:
        """获取单条文本的向量"""
        result = self.get_embeddings([text])
        return result[0] if len(result) > 0 else np.array([])

    def _get_deepseek_embeddings(self, texts: List[str]) -> np.ndarray:
        """调用 DeepSeek Embedding API"""
        import json

        url = f"{self._base_url.rstrip('/')}/embeddings"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        data = {
            "model": self._model_name,
            "input": texts,
        }

        response = self._client.post(url, headers=headers, content=json.dumps(data))
        response.raise_for_status()
        result = response.json()

        embeddings = [item["embedding"] for item in result["data"]]
        return np.array(embeddings, dtype=np.float32)


# 全局实例
embedding_manager = EmbeddingManager()
