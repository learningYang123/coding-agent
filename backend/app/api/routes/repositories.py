"""
仓库管理路由 - 创建、导入 Git、权限配置
"""
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from typing import Optional

from app.db.database import get_db_session
from app.api.dependencies import get_current_user, require_admin
from app.models.user import User
from app.models.repository import Repository, UserRepoPermission
from app.schemas.repository import (
    RepositoryCreate,
    RepositoryUpdate,
    RepositoryResponse,
    RepoPermissionCreate,
    RepoPermissionResponse,
)
from app.rag.git_service import git_service
from app.core.logging import get_logger

logger = get_logger()

router = APIRouter(prefix="/repositories", tags=["仓库管理"])


async def _get_accessible_repo_ids(user: User, db: AsyncSession) -> list[int]:
    """获取用户可访问的仓库 ID 列表"""
    if user.is_admin:
        result = await db.execute(select(Repository.id))
        return list(result.scalars().all())

    # 有权限的仓库
    result = await db.execute(
        select(UserRepoPermission.repo_id).where(
            UserRepoPermission.user_id == user.id,
            UserRepoPermission.can_read == True,
        )
    )
    permitted_ids = list(result.scalars().all())

    # 加上公开仓库
    result = await db.execute(
        select(Repository.id).where(Repository.is_public == True)
    )
    public_ids = list(result.scalars().all())

    return list(set(permitted_ids + public_ids))


@router.get("", response_model=list[RepositoryResponse])
async def list_repositories(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """获取可访问的仓库列表"""
    accessible_ids = await _get_accessible_repo_ids(current_user, db)

    query = select(Repository)
    if not current_user.is_admin:
        query = query.where(Repository.id.in_(accessible_ids))

    result = await db.execute(query.order_by(Repository.created_at.desc()))
    repos = result.scalars().all()
    return [RepositoryResponse.model_validate(r) for r in repos]


@router.post("", response_model=RepositoryResponse)
async def create_repository(
    request: RepositoryCreate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
):
    """创建新仓库"""
    # 检查名称
    result = await db.execute(
        select(Repository).where(Repository.name == request.name)
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="仓库名已存在")

    repo = Repository(
        name=request.name,
        description=request.description,
        git_url=request.git_url,
        local_path=request.local_path,
        default_branch=request.default_branch,
        languages=request.languages,
        status="pending",
    )
    db.add(repo)
    await db.commit()
    await db.refresh(repo)

    # 给创建者默认权限
    permission = UserRepoPermission(
        user_id=current_user.id,
        repo_id=repo.id,
        can_read=True,
        can_write=True,
    )
    db.add(permission)
    await db.commit()

    return RepositoryResponse.model_validate(repo)


@router.get("/{repo_id}", response_model=RepositoryResponse)
async def get_repository(
    repo_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """获取仓库详情"""
    result = await db.execute(select(Repository).where(Repository.id == repo_id))
    repo = result.scalar_one_or_none()
    if not repo:
        raise HTTPException(status_code=404, detail="仓库不存在")

    # 权限检查
    if not current_user.is_admin and not repo.is_public:
        accessible_ids = await _get_accessible_repo_ids(current_user, db)
        if repo_id not in accessible_ids:
            raise HTTPException(status_code=403, detail="无访问权限")

    return RepositoryResponse.model_validate(repo)


@router.put("/{repo_id}", response_model=RepositoryResponse)
async def update_repository(
    repo_id: int,
    request: RepositoryUpdate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
):
    """更新仓库"""
    result = await db.execute(select(Repository).where(Repository.id == repo_id))
    repo = result.scalar_one_or_none()
    if not repo:
        raise HTTPException(status_code=404, detail="仓库不存在")

    for field, value in request.model_dump(exclude_unset=True).items():
        setattr(repo, field, value)

    await db.commit()
    await db.refresh(repo)
    return RepositoryResponse.model_validate(repo)


@router.delete("/{repo_id}")
async def delete_repository(
    repo_id: int,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
):
    """删除仓库（包括向量数据）"""
    from app.rag.vector_store import faiss_store

    result = await db.execute(select(Repository).where(Repository.id == repo_id))
    repo = result.scalar_one_or_none()
    if not repo:
        raise HTTPException(status_code=404, detail="仓库不存在")

    # 删除向量
    faiss_store.delete_by_repo(repo_id)

    # 删除数据库记录
    await db.delete(repo)
    await db.commit()

    return {"message": "仓库已删除"}


@router.post("/{repo_id}/sync")
async def sync_repository(
    repo_id: int,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
):
    """同步/索引仓库"""
    from pathlib import Path

    result = await db.execute(select(Repository).where(Repository.id == repo_id))
    repo = result.scalar_one_or_none()
    if not repo:
        raise HTTPException(status_code=404, detail="仓库不存在")

    # 更新状态
    repo.status = "indexing"
    await db.commit()

    try:
        # 获取仓库路径
        if repo.local_path:
            repo_path = Path(repo.local_path)
        elif repo.git_url:
            repo_path = await git_service.clone_or_update(
                repo_id=repo.id,
                git_url=repo.git_url,
                branch=repo.default_branch,
            )
        else:
            raise HTTPException(status_code=400, detail="仓库没有 git_url 或 local_path")

        # 处理仓库
        stats = await git_service.process_repository(repo.id, repo_path, db)

        return {"message": "同步完成", "stats": stats}

    except Exception as e:
        repo.status = "error"
        await db.commit()
        logger.error(f"同步仓库失败: {e}")
        raise HTTPException(status_code=500, detail=f"同步失败: {str(e)}")


# === 权限管理 ===

@router.get("/{repo_id}/permissions", response_model=list[RepoPermissionResponse])
async def list_permissions(
    repo_id: int,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
):
    """获取仓库的权限列表"""
    result = await db.execute(
        select(UserRepoPermission).where(UserRepoPermission.repo_id == repo_id)
    )
    perms = result.scalars().all()
    return [RepoPermissionResponse.model_validate(p) for p in perms]


@router.post("/{repo_id}/permissions", response_model=RepoPermissionResponse)
async def grant_permission(
    repo_id: int,
    request: RepoPermissionCreate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
):
    """授予用户仓库权限"""
    # 检查是否已存在
    result = await db.execute(
        select(UserRepoPermission).where(
            UserRepoPermission.user_id == request.user_id,
            UserRepoPermission.repo_id == repo_id,
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        existing.can_read = request.can_read
        existing.can_write = request.can_write
        await db.commit()
        await db.refresh(existing)
        return RepoPermissionResponse.model_validate(existing)

    perm = UserRepoPermission(
        user_id=request.user_id,
        repo_id=repo_id,
        can_read=request.can_read,
        can_write=request.can_write,
    )
    db.add(perm)
    await db.commit()
    await db.refresh(perm)
    return RepoPermissionResponse.model_validate(perm)


@router.delete("/{repo_id}/permissions/{user_id}")
async def revoke_permission(
    repo_id: int,
    user_id: int,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
):
    """撤销用户权限"""
    await db.execute(
        delete(UserRepoPermission).where(
            UserRepoPermission.repo_id == repo_id,
            UserRepoPermission.user_id == user_id,
        )
    )
    await db.commit()
    return {"message": "权限已撤销"}


# 导出为可复用的函数
get_accessible_repo_ids = _get_accessible_repo_ids
