"""Authenticated CRUD, discovery and connection tests for user model profiles."""
import asyncio
import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.dependencies import get_current_user
from app.core.model_keys import encrypt_api_key, decrypt_api_key
from app.db.database import get_db_session
from app.models.model_config import ModelConfig
from app.models.user import User
from app.schemas.model_config import ModelConfigInput, ModelConfigResponse
from app.rag.llm_service import LLMService, LLMError
from app.rag.model_registry import PROVIDERS, get_provider, owned_model, service_for_model

router = APIRouter(prefix="/models", tags=["模型设置"])


def public_profile(profile: ModelConfig) -> ModelConfigResponse:
    return ModelConfigResponse(id=profile.id, name=profile.name, provider=profile.provider, base_url=profile.base_url, model=profile.model, has_api_key=bool(profile.encrypted_api_key), is_default=profile.is_default)


def effective_key(body: ModelConfigInput, existing: ModelConfig | None = None) -> str:
    if body.api_key is not None:
        return body.api_key.get_secret_value()
    try:
        return decrypt_api_key(existing.encrypted_api_key) if existing else ""
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def validate_connection(body: ModelConfigInput, key: str):
    provider = get_provider(body.provider)
    if provider["requires_api_key"] and not key:
        raise HTTPException(status_code=400, detail="该供应商需要 API Key")


@router.get("/providers")
async def providers(user: User = Depends(get_current_user)):
    return PROVIDERS


@router.get("", response_model=list[ModelConfigResponse])
async def list_models(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db_session)):
    result = await db.execute(select(ModelConfig).where(ModelConfig.user_id == user.id).order_by(ModelConfig.is_default.desc(), ModelConfig.id))
    return [public_profile(profile) for profile in result.scalars()]


@router.post("", response_model=ModelConfigResponse, status_code=201)
async def create_model(body: ModelConfigInput, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db_session)):
    key = effective_key(body)
    validate_connection(body, key)
    first = (await db.execute(select(ModelConfig.id).where(ModelConfig.user_id == user.id).limit(1))).first() is None
    is_default = body.is_default or first
    if is_default:
        await db.execute(update(ModelConfig).where(ModelConfig.user_id == user.id).values(is_default=False))
    profile = ModelConfig(user_id=user.id, **body.model_dump(exclude={"api_key", "is_default"}), encrypted_api_key=encrypt_api_key(key), is_default=is_default)
    db.add(profile)
    await db.commit()
    await db.refresh(profile)
    return public_profile(profile)


@router.put("/{model_id}", response_model=ModelConfigResponse)
async def edit_model(model_id: int, body: ModelConfigInput, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db_session)):
    profile = await owned_model(db, user.id, model_id)
    if body.provider != profile.provider and body.api_key is None and profile.encrypted_api_key:
        raise HTTPException(status_code=400, detail="更换供应商时请重新填写密钥，避免沿用其他平台密钥")
    key = effective_key(body, profile)
    validate_connection(body, key)
    if body.is_default:
        await db.execute(update(ModelConfig).where(ModelConfig.user_id == user.id).values(is_default=False))
    for field, value in body.model_dump(exclude={"api_key", "is_default"}).items():
        setattr(profile, field, value)
    profile.encrypted_api_key = encrypt_api_key(key)
    if body.is_default:
        profile.is_default = True
    await db.commit()
    await db.refresh(profile)
    return public_profile(profile)


@router.post("/{model_id}/default", response_model=ModelConfigResponse)
async def set_default(model_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db_session)):
    profile = await owned_model(db, user.id, model_id)
    await db.execute(update(ModelConfig).where(ModelConfig.user_id == user.id).values(is_default=False))
    profile.is_default = True
    await db.commit()
    await db.refresh(profile)
    return public_profile(profile)


@router.delete("/{model_id}", status_code=204)
async def delete_model(model_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db_session)):
    profile = await owned_model(db, user.id, model_id)
    was_default = profile.is_default
    await db.delete(profile)
    await db.flush()
    if was_default:
        replacement = (await db.execute(select(ModelConfig).where(ModelConfig.user_id == user.id).order_by(ModelConfig.id).limit(1))).scalar_one_or_none()
        if replacement:
            replacement.is_default = True
    await db.commit()


async def test_service(service: LLMService):
    try:
        prompt = "Reply only with the word OK. Do not explain."
        local_qwen = service._provider == "ollama" and "qwen" in service._model.lower()
        if local_qwen:
            prompt += " /no_think"
        answer = await asyncio.wait_for(service.chat([{"role": "user", "content": prompt}], max_tokens=256 if local_qwen else 1024), timeout=90)
        return {"success": True, "message": "连接成功，模型已返回响应", "response": answer[:160]}
    except (asyncio.TimeoutError, httpx.TimeoutException):
        raise HTTPException(status_code=504, detail="连接超时，请检查服务地址或本地模型是否已启动")
    except (LLMError, httpx.RequestError, ValueError) as exc:
        detail = str(exc) if isinstance(exc, LLMError) else "连接失败，请检查 API 地址、网络和模型服务"
        raise HTTPException(status_code=400, detail=detail)
    finally:
        await service.close()


@router.post("/test-connection")
async def test_draft(body: ModelConfigInput, model_id: int | None = None, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db_session)):
    existing = await owned_model(db, user.id, model_id) if model_id is not None else None
    if existing and existing.provider != body.provider and body.api_key is None and existing.encrypted_api_key:
        raise HTTPException(status_code=400, detail="更换供应商时请重新填写密钥")
    key = effective_key(body, existing)
    validate_connection(body, key)
    return await test_service(LLMService(provider=body.provider, base_url=body.base_url, model=body.model, api_key=key, allow_mock=False))


@router.post("/{model_id}/test")
async def test_saved(model_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db_session)):
    return await test_service(service_for_model(await owned_model(db, user.id, model_id)))


@router.post("/discover")
async def discover_models(body: ModelConfigInput, model_id: int | None = None, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db_session)):
    existing = await owned_model(db, user.id, model_id) if model_id is not None else None
    if existing and existing.provider != body.provider and body.api_key is None and existing.encrypted_api_key:
        raise HTTPException(status_code=400, detail="更换供应商时请重新填写密钥")
    key = effective_key(body, existing)
    validate_connection(body, key)
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(f"{body.base_url}/models", headers=headers)
            LLMService.check_response(response)
            models = response.json().get("data", [])
            return {"models": sorted({item["id"] for item in models if isinstance(item, dict) and isinstance(item.get("id"), str)})}
    except LLMError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (httpx.RequestError, ValueError, TypeError, AttributeError):
        raise HTTPException(status_code=400, detail="无法获取模型列表，服务可能不支持该接口，请手动填写模型 ID")
