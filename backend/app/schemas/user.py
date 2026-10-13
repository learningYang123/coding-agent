"""
用户相关 Schema
"""
from datetime import datetime
from typing import Optional, Literal
from pydantic import BaseModel, EmailStr, Field


class UserLogin(BaseModel):
    """登录请求"""
    username: str = Field(..., min_length=3, max_length=64)
    password: str = Field(..., min_length=6)


class UserRegister(BaseModel):
    """普通用户自助注册"""
    username: str = Field(..., min_length=3, max_length=64)
    email: EmailStr
    full_name: Optional[str] = None
    password: str = Field(..., min_length=6)


class AdminUserCreate(BaseModel):
    """管理员创建用户（可指定角色）"""
    username: str = Field(..., min_length=3, max_length=64)
    email: EmailStr
    full_name: Optional[str] = None
    password: str = Field(..., min_length=6)
    role: Literal["admin", "developer"] = "developer"


class AdminUserUpdate(BaseModel):
    """管理员编辑用户"""
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    role: Optional[Literal["admin", "developer"]] = None
    is_active: Optional[bool] = None


class AdminPasswordReset(BaseModel):
    """管理员重置用户密码"""
    new_password: str = Field(..., min_length=6)


class UserResponse(BaseModel):
    """用户响应"""
    id: int
    username: str
    email: str
    full_name: Optional[str] = None
    role: str
    is_active: bool
    avatar_url: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    """Token 响应"""
    access_token: str
    token_type: str = "bearer"
    user: UserResponse
