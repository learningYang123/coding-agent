"""
数据库连接和会话管理
"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker, AsyncEngine
from sqlalchemy.orm import DeclarativeBase
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger()


def create_engine() -> AsyncEngine:
    """创建异步数据库引擎"""
    connect_args = {}
    if settings.is_sqlite:
        connect_args["check_same_thread"] = False
        connect_args["timeout"] = 30

    engine = create_async_engine(
        settings.DATABASE_URL,
        echo=settings.DEBUG,
        connect_args=connect_args,
        future=True,
    )
    logger.info(f"数据库引擎创建成功: {settings.DATABASE_URL}")
    return engine


# 全局引擎和会话工厂
engine = create_engine()
async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    """所有 ORM 模型的基类"""
    pass


async def get_db_session():
    """FastAPI 依赖注入 - 获取数据库会话"""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db():
    """初始化数据库 - 创建所有表"""
    from app.models import user, repository, document, conversation, model_config  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("数据库表初始化完成")
