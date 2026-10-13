"""
对话和问答相关 Schema
"""
from datetime import datetime
from typing import Optional, List, Any
from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    """单条消息"""
    role: str = Field(..., pattern="^(user|assistant|system)$")
    content: str


class ChatRequest(BaseModel):
    """问答请求"""
    query: str = Field(..., min_length=1, max_length=4000)
    conversation_id: Optional[int] = None
    model_id: Optional[int] = Field(default=None, gt=0)
    error_log: Optional[str] = Field(default=None, max_length=20000)
    mode: str = Field(default="rag", pattern="^(rag|agent)$")
    repo_ids: Optional[List[int]] = None  # 指定检索仓库
    history: Optional[List[ChatMessage]] = None  # 历史消息（简化场景）


class SourceCode(BaseModel):
    """引用的代码来源"""
    repo_id: int
    repo_name: str
    file_path: str
    chunk_type: Optional[str] = None
    chunk_name: Optional[str] = None
    start_line: Optional[int] = None
    end_line: Optional[int] = None
    content: str
    score: float


class ChatResponse(BaseModel):
    """非流式问答响应"""
    answer: str
    sources: List[SourceCode] = []
    thinking: Optional[str] = None


class ConversationCreate(BaseModel):
    """创建对话"""
    title: Optional[str] = None
    mode: str = "rag"
    repo_ids: Optional[List[int]] = None


class ConversationResponse(BaseModel):
    """对话响应"""
    id: int
    title: Optional[str] = None
    mode: str
    repo_ids: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class MessageResponse(BaseModel):
    """消息响应"""
    id: int
    role: str
    content: str
    sources: Optional[str] = None
    thinking: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ErrorAnalyzeRequest(BaseModel):
    """错误日志分析请求"""
    error_log: str = Field(..., description="完整的错误堆栈或日志内容")
    question: Optional[str] = Field(default=None, description="附加的问题或补充说明")
    repo_ids: Optional[List[int]] = None
    model_id: Optional[int] = Field(default=None, gt=0)


class RunCodeRequest(BaseModel):
    """代码执行请求"""
    code: str = Field(..., description="要执行的 Python 代码")
