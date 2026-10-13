"""
文档和代码分块模型
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Float, Index
from sqlalchemy.orm import relationship
from app.db.database import Base


class Document(Base):
    """文档/源文件表"""
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    repo_id = Column(Integer, ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False, index=True)
    file_path = Column(String(512), nullable=False)
    file_name = Column(String(256), nullable=False)
    file_type = Column(String(32), nullable=False)  # py/java/js/md/txt
    content = Column(Text, nullable=True)  # 原始内容（可选存储）
    size_bytes = Column(Integer, default=0, nullable=False)
    line_count = Column(Integer, default=0, nullable=False)
    git_commit = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # 关系
    repository = relationship("Repository", back_populates="documents")
    chunks = relationship("CodeChunk", back_populates="document", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_doc_repo_path", "repo_id", "file_path"),
    )


class CodeChunk(Base):
    """代码分块表"""
    __tablename__ = "code_chunks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    repo_id = Column(Integer, ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False, index=True)
    chunk_index = Column(Integer, nullable=False)  # 在文件中的序号
    chunk_type = Column(String(32), nullable=False)  # function/class/method/comment/text
    chunk_name = Column(String(256), nullable=True)  # 函数名/类名等
    content = Column(Text, nullable=False)  # 分块内容
    start_line = Column(Integer, nullable=True)
    end_line = Column(Integer, nullable=True)
    token_count = Column(Integer, default=0, nullable=False)
    vector_id = Column(String(64), nullable=True)  # 向量库中的 ID
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # 关系
    document = relationship("Document", back_populates="chunks")

    __table_args__ = (
        Index("ix_chunk_repo_type", "repo_id", "chunk_type"),
    )
