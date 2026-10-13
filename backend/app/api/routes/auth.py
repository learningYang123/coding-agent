"""
认证相关路由 - 登录、注册、用户管理
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.database import get_db_session
from app.core.security import hash_password, verify_password, create_access_token
from app.api.dependencies import get_current_user, require_admin
from app.models.user import User
from app.schemas.user import (
    UserLogin,
    UserRegister,
    AdminUserCreate,
    AdminUserUpdate,
    AdminPasswordReset,
    UserResponse,
    TokenResponse,
)

router = APIRouter(prefix="/auth", tags=["认证"])


# ==================== 公共接口 ====================

@router.post("/login", response_model=TokenResponse)
async def login(request: UserLogin, db: AsyncSession = Depends(get_db_session)):
    """用户登录"""
    result = await db.execute(
        select(User).where(User.username == request.username)
    )
    user = result.scalar_one_or_none()

    if not user or not verify_password(request.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="用户已被禁用，请联系管理员",
        )

    access_token = create_access_token(data={"sub": user.id, "role": user.role})
    user_response = UserResponse.model_validate(user)

    return TokenResponse(access_token=access_token, user=user_response)


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def self_register(
    request: UserRegister,
    db: AsyncSession = Depends(get_db_session),
):
    """普通用户自助注册（角色固定为 developer）"""
    # 检查用户名是否已存在
    result = await db.execute(
        select(User).where(User.username == request.username)
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="用户名已被使用")

    # 检查邮箱
    result = await db.execute(select(User).where(User.email == request.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="邮箱已被使用")

    user = User(
        username=request.username,
        email=request.email,
        full_name=request.full_name,
        hashed_password=hash_password(request.password),
        role="developer",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    return UserResponse.model_validate(user)


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    """获取当前登录用户信息"""
    return UserResponse.model_validate(current_user)


# ==================== 管理员用户管理 ====================

@router.get("/admin/users", response_model=list[UserResponse])
async def admin_list_users(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
):
    """管理员 - 获取所有用户列表"""
    result = await db.execute(select(User).order_by(User.id))
    users = result.scalars().all()
    return [UserResponse.model_validate(u) for u in users]


@router.post("/admin/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def admin_create_user(
    request: AdminUserCreate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
):
    """管理员 - 创建用户（可指定角色）"""
    # 检查用户名
    result = await db.execute(
        select(User).where(User.username == request.username)
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="用户名已被使用")

    # 检查邮箱
    result = await db.execute(select(User).where(User.email == request.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="邮箱已被使用")

    user = User(
        username=request.username,
        email=request.email,
        full_name=request.full_name,
        hashed_password=hash_password(request.password),
        role=request.role,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    return UserResponse.model_validate(user)


@router.put("/admin/users/{user_id}", response_model=UserResponse)
async def admin_update_user(
    user_id: int,
    request: AdminUserUpdate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
):
    """管理员 - 编辑用户（修改信息、角色、启禁用）"""
    if user_id == current_user.id and request.role and request.role != "admin":
        raise HTTPException(
            status_code=400, detail="不能把自己的管理员权限降为普通用户"
        )

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    data = request.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(user, field, value)

    await db.commit()
    await db.refresh(user)

    return UserResponse.model_validate(user)


@router.post("/admin/users/{user_id}/reset-password", response_model=UserResponse)
async def admin_reset_password(
    user_id: int,
    request: AdminPasswordReset,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
):
    """管理员 - 重置用户密码"""
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="不能用此接口重置自己的密码")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    user.hashed_password = hash_password(request.new_password)
    await db.commit()
    await db.refresh(user)

    return UserResponse.model_validate(user)


@router.delete("/admin/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def admin_delete_user(
    user_id: int,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
):
    """管理员 - 删除用户"""
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="不能删除自己")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    await db.delete(user)
    await db.commit()
    return None
