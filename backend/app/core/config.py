"""
全局配置模块 - 使用 pydantic-settings 管理环境变量
"""
from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """应用全局配置"""

    # ===== 应用基础信息 =====
    APP_NAME: str = "企业代码智能助手"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True

    # ===== 数据库 =====
    DATABASE_URL: str = "sqlite+aiosqlite:///./data/app.db"

    # ===== JWT =====
    SECRET_KEY: str = "dev-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24小时

    # ===== LLM 配置 =====
    LLM_PROVIDER: str = "ollama"
    LLM_BASE_URL: str = "http://localhost:11434/v1"
    LLM_API_KEY: str = "ollama"
    LLM_MODEL: str = "qwen3:4b"
    LLM_TEMPERATURE: float = 0.2
    LLM_MAX_TOKENS: int = 4096
    MODEL_ENCRYPTION_KEY: str = ""
    MODEL_ENCRYPTION_KEY_FILE: str = "./data/.model-key"

    # ===== Embedding =====
    EMBEDDING_PROVIDER: str = "local"
    EMBEDDING_MODEL_PATH: str = "./data/embeddings/all-MiniLM-L6-v2"
    EMBEDDING_API_KEY: str = ""
    EMBEDDING_MODEL: str = "text-embedding-v2"

    # ===== 向量库 =====
    VECTOR_STORE: str = "faiss"
    FAISS_INDEX_PATH: str = "./data/faiss"
    MILVUS_HOST: str = "localhost"
    MILVUS_PORT: int = 19530

    # ===== 沙箱 =====
    SANDBOX_ENABLED: bool = True
    SANDBOX_TIMEOUT: int = 30
    SANDBOX_MAX_MEMORY_MB: int = 256

    # ===== Git =====
    GIT_EXECUTABLE: str = "git"
    GIT_CLONE_TIMEOUT: int = 120
    GIT_MAX_REPO_SIZE_MB: int = 500

    # ===== 代码分块 =====
    CHUNK_MAX_SIZE: int = 1500
    CHUNK_OVERLAP: int = 200

    # ===== 管理员默认账号 =====
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = "admin123"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    @property
    def is_sqlite(self) -> bool:
        return self.DATABASE_URL.startswith("sqlite")

    @property
    def embedding_dimension(self) -> int:
        """根据模型类型返回向量维度"""
        if self.EMBEDDING_PROVIDER == "local":
            return 384  # all-MiniLM-L6-v2
        return 1024  # deepseek text-embedding-v2


settings = Settings()
