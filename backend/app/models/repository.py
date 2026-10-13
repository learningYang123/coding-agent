"""
代码仓库模型
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from app.db.database import Base


class Repository(Base):
    """Git 代码仓库表"""
    __tablename__ = "repositories"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(128), unique=True, nullable=False, index=True)
    description = Column(Text, nullable=True)
    git_url = Column(String(512), nullable=True)  # Git 仓库地址
    local_path = Column(String(512), nullable=True)  # 本地克隆路径
    default_branch = Column(String(64), default="main", nullable=False)
    languages = Column(String(256), nullable=True)  # 逗号分隔的语言类型 python,java,js
    status = Column(String(32), default="pending", nullable=False)  # pending/indexing/ready/error
    total_files = Column(Integer, default=0, nullable=False)
    total_chunks = Column(Integer, default=0, nullable=False)
    is_public = Column(Boolean, default=False, nullable=False)
    last_synced_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    # 关系
    permissions = relationship("UserRepoPermission", back_populates="repository", cascade="all, delete-orphan")
    documents = relationship("Document", back_populates="repository", cascade="all, delete-orphan")


class UserRepoPermission(Base):
    """用户-仓库权限绑定表"""
    __tablename__ = "user_repo_permissions"
    __table_args__ = (
        UniqueConstraint("user_id", "repo_id", name="uq_user_repo"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    repo_id = Column(Integer, ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False, index=True)
    can_read = Column(Boolean, default=True, nullable=False)
    can_write = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # 关系
    user = relationship("User", back_populates="repo_permissions")
    repository = relationship("Repository", back_populates="permissions")
