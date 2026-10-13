"""Provider presets and per-request connection resolution."""
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.model_keys import decrypt_api_key
from app.models.model_config import ModelConfig
from app.rag.llm_service import LLMService


PROVIDERS = [
    {"id": "deepseek", "name": "DeepSeek", "base_url": "https://api.deepseek.com", "models": ["deepseek-flash", "deepseek-v4-pro"], "requires_api_key": True, "description": "使用 DeepSeek 开放平台密钥", "docs_url": "https://api-docs.deepseek.com/"},
    {"id": "ollama", "name": "Ollama 本地", "base_url": "http://localhost:11434/v1", "models": ["qwen3:4b", "qwen3:8b", "gpt-oss:20b"], "requires_api_key": False, "description": "无需密钥；地址指向后端所在电脑的 Ollama，模型须已下载", "docs_url": "https://docs.ollama.com/api/openai-compatibility"},
    {"id": "zhipu", "name": "智谱 GLM", "base_url": "https://open.bigmodel.cn/api/paas/v4", "models": ["glm-5.3", "glm-5.3-flash", "glm-5.2"], "requires_api_key": True, "description": "使用智谱开放平台密钥；Coding Plan 请使用对应专用地址", "docs_url": "https://docs.bigmodel.cn/cn/guide/develop/openai/introduction"},
    {"id": "qwen", "name": "千问 · 阿里云百炼", "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1", "models": ["qwen-plus", "qwen-turbo", "qwen-max"], "requires_api_key": True, "description": "预置北京兼容地址；请按密钥地域填写控制台的地址，也支持业务空间专属域名", "docs_url": "https://www.alibabacloud.com/help/en/model-studio/compatibility-of-openai-with-dashscope"},
    {"id": "openai", "name": "OpenAI", "base_url": "https://api.openai.com/v1", "models": ["gpt-4.1-mini", "gpt-4.1", "gpt-4o"], "requires_api_key": True, "description": "支持 Chat Completions 及推理模型，可手动输入模型 ID", "docs_url": "https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create"},
    {"id": "siliconflow", "name": "硅基流动 SiliconFlow", "base_url": "https://api.siliconflow.cn/v1", "models": [], "requires_api_key": True, "description": "填写平台完整模型 ID，可点击获取模型列表", "docs_url": "https://docs.siliconflow.cn/docs/userguide/quickstart"},
    {"id": "openrouter", "name": "OpenRouter", "base_url": "https://openrouter.ai/api/v1", "models": [], "requires_api_key": True, "description": "支持聚合平台模型；填写包含供应商前缀的完整 ID", "docs_url": "https://openrouter.ai/docs/quickstart"},
    {"id": "gemini", "name": "Google Gemini", "base_url": "https://generativelanguage.googleapis.com/v1beta/openai", "models": ["gemini-3.8-flash"], "requires_api_key": True, "description": "使用 Gemini API 密钥，通过 OpenAI 兼容接口接入", "docs_url": "https://ai.google.dev/gemini-api/docs/openai"},
    {"id": "custom", "name": "自定义 / One API / New API", "base_url": "", "models": [], "requires_api_key": False, "description": "适配其他 OpenAI 兼容服务和中转站；填写 Base URL、模型 ID 和所需密钥", "docs_url": ""},
]


def get_provider(provider: str) -> dict:
    for item in PROVIDERS:
        if item["id"] == provider:
            return item
    raise HTTPException(status_code=400, detail="不支持的供应商，请选择自定义兼容服务")


async def owned_model(db: AsyncSession, user_id: int, model_id: int) -> ModelConfig:
    result = await db.execute(select(ModelConfig).where(ModelConfig.id == model_id, ModelConfig.user_id == user_id))
    profile = result.scalar_one_or_none()
    if profile is None:
        raise HTTPException(status_code=404, detail="模型配置不存在")
    return profile


def service_for_model(profile: ModelConfig) -> LLMService:
    try:
        key = decrypt_api_key(profile.encrypted_api_key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return LLMService(provider=profile.provider, base_url=profile.base_url, api_key=key, model=profile.model, allow_mock=False)


async def resolve_llm(db: AsyncSession, user_id: int, model_id: int | None) -> LLMService:
    if model_id is not None:
        return service_for_model(await owned_model(db, user_id, model_id))
    result = await db.execute(select(ModelConfig).where(ModelConfig.user_id == user_id, ModelConfig.is_default.is_(True)).order_by(ModelConfig.id).limit(1))
    profile = result.scalar_one_or_none()
    return service_for_model(profile) if profile else LLMService()
