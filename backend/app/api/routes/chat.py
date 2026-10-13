"""
对话问答路由 - RAG 和 Agent 双模式，支持 SSE 流式输出
"""
import json
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import asyncio

from app.db.database import get_db_session
from app.api.dependencies import get_current_user
from app.api.routes.repositories import get_accessible_repo_ids
from app.models.user import User
from app.models.conversation import Conversation, Message
from app.schemas.chat import ChatRequest, ConversationCreate, ConversationResponse, MessageResponse, ErrorAnalyzeRequest, RunCodeRequest
from app.rag.pipeline import RAGPipeline
from app.agent.agent import CodeAgent
from app.rag.model_registry import resolve_llm
from app.rag.llm_service import LLMError
import httpx
from app.agent.tools import agent_tools
from app.utils.sse import SSEBuffer, make_token_event, make_sources_event, make_thinking_event, make_agent_step_event, make_done_event, make_error_event
from app.core.logging import get_logger

logger = get_logger()

router = APIRouter(prefix="/chat", tags=["对话问答"])


async def _complete_model_call(llm, operation):
    try:
        return await operation
    except LLMError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="模型请求超时，请检查服务状态")
    except httpx.RequestError:
        raise HTTPException(status_code=502, detail="无法连接模型服务，请检查模型设置和网络")
    finally:
        await llm.close()


async def _build_history(db: AsyncSession, conversation_id: Optional[int], history: Optional[list]) -> list:
    """构建 LLM 历史消息"""
    messages = []

    # 如果有 conversation_id，从数据库加载
    if conversation_id:
        result = await db.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.desc())
            .limit(12)
        )
        db_msgs = reversed(list(result.scalars().all()))
        for msg in db_msgs:
            if msg.role in ("user", "assistant"):
                messages.append({"role": msg.role, "content": msg.content})

    # 如果前端直接传了 history，也合并进去
    if history:
        for h in history:
            if hasattr(h, "model_dump"):
                h = h.model_dump()
            messages.append({"role": h.get("role", "user"), "content": h.get("content", "")})

    return messages[-10:]  # 最多 10 条


async def _ensure_conversation(
    db: AsyncSession,
    user: User,
    conversation_id: Optional[int],
    mode: str,
    repo_ids: Optional[List[int]],
) -> Conversation:
    """确保对话存在"""
    if conversation_id:
        result = await db.execute(
            select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.user_id == user.id,
            )
        )
        conv = result.scalar_one_or_none()
        if conv:
            return conv

    # 创建新对话
    title = None
    conv = Conversation(
        user_id=user.id,
        title=title,
        mode=mode,
        repo_ids=",".join(str(r) for r in repo_ids) if repo_ids else None,
    )
    db.add(conv)
    await db.commit()
    await db.refresh(conv)
    return conv


@router.post("/ask")
async def ask(
    request: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """
    非流式问答（备用接口）
    """
    llm = await resolve_llm(db, current_user.id, request.model_id)
    rag_pipeline = RAGPipeline(llm)
    code_agent = CodeAgent(llm)
    # 权限过滤
    allowed_ids = await get_accessible_repo_ids(current_user, db)
    repo_filter = request.repo_ids or allowed_ids
    repo_filter = [r for r in repo_filter if r in allowed_ids or current_user.is_admin]

    history = await _build_history(db, request.conversation_id, request.history)

    if request.mode == "agent":
        result = await _complete_model_call(llm, code_agent.run(
            query=request.query,
            error_log=request.error_log,
            allowed_repo_ids=repo_filter,
        ))
        sources_serializable = [
            {k: v for k, v in s.items() if k != "content"}
            for s in result["sources"]
        ]
        return {
            "answer": result["answer"],
            "sources": sources_serializable,
            "thinking": result["thinking"],
        }
    else:
        result = await _complete_model_call(llm, rag_pipeline.answer(
            query=request.query,
            allowed_repo_ids=repo_filter,
            history=history,
        ))
        sources_serializable = [
            {k: v for k, v in s.items() if k != "content"}
            for s in result["sources"]
        ]
        return {
            "answer": result["answer"],
            "sources": sources_serializable,
            "thinking": None,
        }


@router.post("/stream")
async def stream_ask(
    request: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """
    SSE 流式问答接口

    事件类型:
    - sources: 检索到的代码来源列表
    - thinking: Agent 思考过程（Agent 模式）
    - agent_step: Agent 工具调用步骤
    - token: LLM 增量 token
    - done: 生成结束，携带最终 answer
    - error: 错误信息
    """
    llm = await resolve_llm(db, current_user.id, request.model_id)
    rag_pipeline = RAGPipeline(llm)
    code_agent = CodeAgent(llm)
    # 权限过滤
    allowed_ids = await get_accessible_repo_ids(current_user, db)
    repo_filter = request.repo_ids or allowed_ids
    repo_filter = [r for r in repo_filter if r in allowed_ids or current_user.is_admin]

    # 准备对话
    conv = await _ensure_conversation(
        db, current_user, request.conversation_id, request.mode, repo_filter
    )

    # 保存用户消息
    user_msg = Message(
        conversation_id=conv.id,
        role="user",
        content=request.query,
    )
    db.add(user_msg)
    await db.commit()

    # SSE 缓冲区
    buffer = SSEBuffer()
    full_answer_parts = []
    full_sources = []
    full_thinking_parts = []

    # 提前构建 history（在请求 session 关闭之前）
    pre_history = await _build_history(db, conv.id, request.history)

    async def generate_sse():
        """后台生成 SSE 事件"""
        try:
            if request.mode == "agent":
                async for event in code_agent.stream_run(
                    query=request.query,
                    error_log=request.error_log,
                    allowed_repo_ids=repo_filter,
                ):
                    event_type = event["type"]
                    event_data = event["data"]

                    if event_type == "sources":
                        full_sources.extend(event_data)
                        await buffer.put_sources(event_data)

                    elif event_type == "thinking":
                        full_thinking_parts.append(event_data)
                        await buffer.put_thinking(event_data)

                    elif event_type == "agent_step":
                        await buffer.put_agent_step(
                            event_data.get("step", ""),
                            event_data.get("detail"),
                        )

                    elif event_type == "token":
                        full_answer_parts.append(event_data)
                        await buffer.put_token(event_data)

                    elif event_type == "done":
                        await buffer.put_done({
                            "answer": "".join(full_answer_parts),
                            "sources": full_sources,
                            "conversation_id": conv.id,
                        })
            else:
                async for event in rag_pipeline.stream_answer(
                    query=request.query,
                    allowed_repo_ids=repo_filter,
                    history=pre_history,
                ):
                    event_type = event["type"]
                    event_data = event["data"]

                    if event_type == "sources":
                        full_sources.extend(event_data)
                        await buffer.put_sources(event_data)

                    elif event_type == "token":
                        full_answer_parts.append(event_data)
                        await buffer.put_token(event_data)

                    elif event_type == "done":
                        await buffer.put_done({
                            "answer": "".join(full_answer_parts),
                            "sources": full_sources,
                            "conversation_id": conv.id,
                        })

        except Exception as e:
            logger.error(f"流式生成出错: {type(e).__name__}")
            await buffer.put_error(str(e) if isinstance(e, LLMError) else "模型请求失败，请检查模型设置和网络连接")

        finally:
            await llm.close()
            # 用独立 session 保存 assistant 消息（请求 session 可能已关闭）
            from app.db.database import async_session_factory
            final_content = "".join(full_answer_parts)
            if final_content:
                full_sources_str = json.dumps(full_sources[:10], ensure_ascii=False)
                full_thinking_str = "\n".join(full_thinking_parts) or None

                try:
                    async with async_session_factory() as new_session:
                        assistant_msg = Message(
                            conversation_id=conv.id,
                            role="assistant",
                            content=final_content,
                            sources=full_sources_str,
                            thinking=full_thinking_str,
                            token_count=len(full_answer_parts),
                        )
                        new_session.add(assistant_msg)
                        await new_session.commit()
                except Exception as e2:
                    logger.error(f"保存 assistant 消息失败: {e2}")

    # 启动生成协程
    asyncio.create_task(generate_sse())

    # 返回 SSE 流
    async def event_stream():
        async for event in buffer.stream():
            yield event.to_sse_format() + "\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Nginx 反代理时禁用缓冲
        },
    )


# === 报错日志专用接口 ===

@router.post("/analyze-error")
async def analyze_error(
    request_body: ErrorAnalyzeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """
    非流式错误日志分析
    """
    llm = await resolve_llm(db, current_user.id, request_body.model_id)
    code_agent = CodeAgent(llm)
    allowed_ids = await get_accessible_repo_ids(current_user, db)
    repo_filter = request_body.repo_ids or allowed_ids

    result = await _complete_model_call(llm, code_agent.run(
        query=request_body.question or "请分析这个错误并给出修复建议",
        error_log=request_body.error_log,
        allowed_repo_ids=repo_filter,
    ))

    return {
        "answer": result["answer"],
        "thinking": result["thinking"],
        "sources": result["sources"],
        "error_analysis": agent_tools.analyze_error_log(request_body.error_log),
    }


@router.post("/analyze-error/stream")
async def stream_analyze_error(
    request: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """
    流式错误日志分析
    request.query 包含错误日志，request.repo_ids 可选
    """
    llm = await resolve_llm(db, current_user.id, request.model_id)
    code_agent = CodeAgent(llm)
    allowed_ids = await get_accessible_repo_ids(current_user, db)
    repo_filter = request.repo_ids or allowed_ids

    buffer = SSEBuffer()
    full_answer_parts = []
    full_sources = []
    full_thinking_parts = []

    # 先推送错误解析结果
    error_analysis = agent_tools.analyze_error_log(request.query)
    await buffer.put_agent_step("parse_error", error_analysis)

    async def generate():
        try:
            async for event in code_agent.stream_run(
                query=request.query,
                allowed_repo_ids=repo_filter,
            ):
                event_type = event["type"]
                event_data = event["data"]

                if event_type == "sources":
                    full_sources.extend(event_data)
                    await buffer.put_sources(event_data)
                elif event_type == "thinking":
                    full_thinking_parts.append(event_data)
                    await buffer.put_thinking(event_data)
                elif event_type == "agent_step":
                    await buffer.put_agent_step(
                        event_data.get("step", ""),
                        event_data.get("detail"),
                    )
                elif event_type == "token":
                    full_answer_parts.append(event_data)
                    await buffer.put_token(event_data)
                elif event_type == "done":
                    await buffer.put_done({
                        "answer": "".join(full_answer_parts),
                        "sources": full_sources,
                    })
        except Exception as e:
            await buffer.put_error(str(e) if isinstance(e, LLMError) else "模型请求失败，请检查模型设置和网络连接")
        finally:
            await llm.close()

    asyncio.create_task(generate())

    async def event_stream():
        async for event in buffer.stream():
            yield event.to_sse_format() + "\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# === 代码执行 ===

@router.post("/run-code")
async def run_code(
    request_body: RunCodeRequest,
    current_user: User = Depends(get_current_user),
):
    """在沙箱中执行代码"""
    from app.agent.sandbox import sandbox
    result = await sandbox.execute(request_body.code)
    return result


# === 对话管理 ===

@router.post("/conversations", response_model=ConversationResponse)
async def create_conversation(
    request: ConversationCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """创建新对话"""
    conv = Conversation(
        user_id=current_user.id,
        title=request.title,
        mode=request.mode,
        repo_ids=",".join(str(r) for r in request.repo_ids) if request.repo_ids else None,
    )
    db.add(conv)
    await db.commit()
    await db.refresh(conv)
    return ConversationResponse.model_validate(conv)


@router.get("/conversations", response_model=list[ConversationResponse])
async def list_conversations(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """获取当前用户的对话列表"""
    result = await db.execute(
        select(Conversation)
        .where(Conversation.user_id == current_user.id)
        .order_by(Conversation.updated_at.desc())
    )
    convs = result.scalars().all()
    return [ConversationResponse.model_validate(c) for c in convs]


@router.get("/conversations/{conv_id}/messages", response_model=list[MessageResponse])
async def get_messages(
    conv_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """获取对话的消息历史"""
    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conv_id,
            Conversation.user_id == current_user.id,
        )
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="对话不存在")

    result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conv_id)
        .order_by(Message.created_at.asc())
    )
    msgs = result.scalars().all()
    return [MessageResponse.model_validate(m) for m in msgs]


@router.delete("/conversations/{conv_id}")
async def delete_conversation(
    conv_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """删除对话"""
    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conv_id,
            Conversation.user_id == current_user.id,
        )
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="对话不存在")

    await db.delete(conv)
    await db.commit()
    return {"message": "对话已删除"}


# === 沙箱工具测试 ===

@router.get("/sandbox/status")
async def sandbox_status(
    current_user: User = Depends(get_current_user),
):
    """获取沙箱状态"""
    from app.agent.sandbox import sandbox
    return {
        "enabled": sandbox.enabled,
        "timeout": sandbox.timeout,
    }
