"""
FastAPI 主应用入口
"""
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.logging import get_logger
from app.db.database import init_db, engine
from app.core.security import hash_password
from app.models.user import User
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

logger = get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期"""
    # === 启动 ===
    logger.info(f"🚀 {settings.APP_NAME} v{settings.APP_VERSION} 启动中...")

    # 确保数据目录存在
    Path("./data/repos").mkdir(parents=True, exist_ok=True)
    Path("./data/faiss").mkdir(parents=True, exist_ok=True)
    Path("./data/logs").mkdir(parents=True, exist_ok=True)
    Path("./data/embeddings").mkdir(parents=True, exist_ok=True)

    # 初始化数据库
    await init_db()

    # 创建默认管理员
    await ensure_default_admin()

    # 打印向量库统计
    from app.rag.vector_store import faiss_store
    stats = faiss_store.get_stats()
    logger.info(f"📊 向量库统计: {stats}")

    logger.info("✅ 应用启动完成")
    yield

    # === 关闭 ===
    logger.info("🛑 应用关闭中...")
    await engine.dispose()
    logger.info("✅ 应用已关闭")


async def ensure_default_admin():
    """确保默认管理员账号存在"""
    from app.db.database import async_session_factory

    async with async_session_factory() as session:
        result = await session.execute(
            select(User).where(User.username == settings.ADMIN_USERNAME)
        )
        admin = result.scalar_one_or_none()

        if not admin:
            admin = User(
                username=settings.ADMIN_USERNAME,
                email="admin@company.com",
                full_name="系统管理员",
                hashed_password=hash_password(settings.ADMIN_PASSWORD),
                role="admin",
            )
            session.add(admin)
            await session.commit()
            logger.info("初始管理员已创建")
        else:
            logger.info("默认管理员已存在")


def create_app() -> FastAPI:
    """创建 FastAPI 应用"""
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description="企业代码智能助手 - RAG + Agent",
        lifespan=lifespan,
    )

    # CORS 中间件
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # 开发环境允许所有
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["*"],
    )

    # 注册路由
    from app.api.routes.auth import router as auth_router
    from app.api.routes.repositories import router as repos_router
    from app.api.routes.chat import router as chat_router
    from app.api.routes.models import router as models_router

    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(repos_router, prefix="/api/v1")
    app.include_router(chat_router, prefix="/api/v1")
    app.include_router(models_router, prefix="/api/v1")

    @app.get("/")
    async def root():
        return {
            "name": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "status": "running",
            "docs": "/docs",
        }

    @app.get("/api/v1/health")
    async def health():
        from app.rag.vector_store import faiss_store
        return {
            "status": "healthy",
            "vector_store": faiss_store.get_stats(),
        }

    return app


# 全局 app 实例
app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
    )
