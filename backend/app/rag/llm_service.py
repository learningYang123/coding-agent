"""
LLM 服务 - OpenAI 兼容供应商，支持独立连接与流式输出
"""
import json
from typing import AsyncGenerator, Optional, List, Dict
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger()


class LLMError(ValueError):
    """Safe provider errors that do not expose credentials or upstream bodies."""


class LLMService:
    """LLM 服务封装"""

    def __init__(self, *, provider=None, api_key=None, base_url=None, model=None, allow_mock=True):
        self._http_client = None
        self._provider = provider if provider is not None else settings.LLM_PROVIDER
        self._api_key = api_key if api_key is not None else settings.LLM_API_KEY
        self._base_url = (base_url if base_url is not None else settings.LLM_BASE_URL).rstrip("/")
        self._model = model if model is not None else settings.LLM_MODEL
        self._temperature = settings.LLM_TEMPERATURE
        self._max_tokens = settings.LLM_MAX_TOKENS
        # Ollama 等本地 provider 不需要 API Key；只有在线 provider 且没 Key 时才走 Mock
        self._mock = (
            allow_mock and not self._api_key
            and self._provider not in ("ollama", "local")
        )

    def _get_client(self):
        import httpx
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=httpx.Timeout(180.0, connect=15.0))
        return self._http_client

    @staticmethod
    def check_response(response):
        if not response.is_success:
            messages = {401: "密钥无效或已过期", 403: "密钥无权限或所属地域不匹配", 404: "API 地址或模型 ID 不存在", 429: "请求过于频繁或账户额度不足", 400: "模型不支持当前参数，请检查模型 ID", 402: "账户余额不足"}
            raise LLMError(f"模型服务返回 HTTP {response.status_code}：{messages.get(response.status_code, '服务暂时不可用，请稍后重试')}")

    def _headers(self):
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    def _payload(self, messages, stream, temperature, max_tokens):
        short_model = self._model.rsplit("/", 1)[-1].lower()
        reasoning = short_model.startswith(("o1", "o3", "o4", "gpt-5", "gpt-6"))
        data = {"model": self._model, "messages": messages, "stream": stream}
        data["max_completion_tokens" if self._provider == "openai" or reasoning else "max_tokens"] = max_tokens if max_tokens is not None else self._max_tokens
        if not reasoning:
            data["temperature"] = temperature if temperature is not None else self._temperature
        return data

    def chat(
        self,
        messages: List[Dict],
        stream: bool = False,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ):
        """
        调用 LLM

        Args:
            messages: 消息列表 [{"role": "user", "content": "..."}]
            stream: 是否流式
            temperature: 温度
            max_tokens: 最大 token

        Returns:
            stream=False  → coroutine (调用方需要 await)
            stream=True   → AsyncGenerator (调用方需要 async for)
        """
        if self._mock:
            logger.info("使用 Mock LLM 响应")
            if stream:
                return self._mock_stream_response(messages)
            return self._mock_response(messages)

        if stream:
            return self._stream_call(messages, temperature, max_tokens)
        return self._non_stream_call(messages, temperature, max_tokens)

    async def _non_stream_call(
        self,
        messages: List[Dict],
        temperature: Optional[float],
        max_tokens: Optional[int],
    ) -> str:
        """非流式调用 - 返回 coroutine"""
        import httpx

        client = self._get_client()
        url = f"{self._base_url}/chat/completions"
        headers = self._headers()
        data = self._payload(messages, False, temperature, max_tokens)

        response = await client.post(url, headers=headers, content=json.dumps(data))
        self.check_response(response)
        result = response.json()
        choices = result.get("choices") or []
        content = choices[0].get("message", {}).get("content") if choices else None
        if not isinstance(content, str) or not content.strip():
            raise LLMError("模型未返回文本，请检查模型类型或增加输出 token 上限")
        return content

    async def _stream_call(
        self,
        messages: List[Dict],
        temperature: Optional[float],
        max_tokens: Optional[int],
    ) -> AsyncGenerator[str, None]:
        """流式调用 - 返回 AsyncGenerator"""
        client = self._get_client()
        url = f"{self._base_url}/chat/completions"
        headers = self._headers()
        data = self._payload(messages, True, temperature, max_tokens)

        async with client.stream("POST", url, headers=headers, content=json.dumps(data)) as response:
            self.check_response(response)
            has_content = False
            async for line in response.aiter_lines():
                if line.startswith("data:"):
                    payload = line[5:].strip()
                    if payload == "[DONE]":
                        break
                    try:
                        chunk = json.loads(payload)
                        if chunk.get("error"):
                            raise LLMError("模型服务中断了生成，请检查账户额度后重试")
                        choices = chunk.get("choices") or []
                        delta = choices[0].get("delta", {}) if choices else {}
                        content = delta.get("content", "")
                        if content:
                            has_content = True
                            yield content
                    except json.JSONDecodeError:
                        continue
            if not has_content:
                raise LLMError("模型未返回文本，请检查模型类型或增加输出 token 上限")

    async def _mock_response(self, messages: List[Dict]) -> str:
        """Mock 非流式响应"""
        last_msg = messages[-1]["content"] if messages else ""
        return f"[Mock AI 响应] 收到问题: {last_msg[:100]}...\n\n这是一个模拟的 AI 响应。请检查 LLM 配置（provider={self._provider}, base_url={self._base_url}, model={self._model}）。"

    async def _mock_stream_response(self, messages: List[Dict]) -> AsyncGenerator[str, None]:
        """Mock 流式响应"""
        response_text = await self._mock_response(messages)
        # 模拟逐字输出
        for char in response_text:
            yield char

    async def close(self):
        """关闭 HTTP 客户端"""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None


# 全局实例
llm_service = LLMService()
