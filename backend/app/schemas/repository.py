"""
仓库相关 Schema
"""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


class RepositoryCreate(BaseModel):
    """创建仓库"""
    name: str = Field(..., min_length=1, max_length=128)
    description: Optional[str] = None
    git_url: Optional[str] = None
    local_path: Optional[str] = None
    default_branch: str = "main"
    languages: Optional[str] = None


class RepositoryUpdate(BaseModel):
    """更新仓库"""
    name: Optional[str] = None
    description: Optional[str] = None
    git_url: Optional[str] = None
    default_branch: Optional[str] = None
    languages: Optional[str] = None
    is_public: Optional[bool] = None


class RepositoryResponse(BaseModel):
    """仓库响应"""
    id: int
    name: str
    description: Optional[str] = None
    git_url: Optional[str] = None
    languages: Optional[str] = None
    status: str
    total_files: int
    total_chunks: int
    is_public: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class RepoPermissionCreate(BaseModel):
    """创建权限"""
    user_id: int
    repo_id: int
    can_read: bool = True
    can_write: bool = False


class RepoPermissionResponse(BaseModel):
    """权限响应"""
    id: int
    user_id: int
    repo_id: int
    can_read: bool
    can_write: bool

    model_config = {"from_attributes": True}
