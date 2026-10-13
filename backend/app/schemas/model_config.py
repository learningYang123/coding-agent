"""Validated model connection payloads. Responses never include credentials."""
from typing import Optional
from urllib.parse import urlsplit, urlunsplit
from pydantic import BaseModel, Field, SecretStr, field_validator


class ModelConfigInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    provider: str = Field(min_length=1, max_length=32)
    base_url: str = Field(min_length=1, max_length=512)
    model: str = Field(min_length=1, max_length=200)
    api_key: Optional[SecretStr] = None
    is_default: bool = False

    @field_validator("name", "provider", "model", mode="before")
    @classmethod
    def trim_text(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("api_key", mode="before")
    @classmethod
    def trim_key(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("base_url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        value = value.strip().rstrip("/")
        try:
            url = urlsplit(value)
            port = url.port
        except ValueError:
            raise ValueError("请输入有效的 API 地址")
        if url.scheme not in ("http", "https") or not url.hostname or url.username or url.password or url.query or url.fragment:
            raise ValueError("API 地址须为 http(s) 地址，不含密钥、查询参数或片段")
        if any(char.isspace() for char in value) or "{" in value or "}" in value:
            raise ValueError("请将地址中的占位符替换为实际值")
        path = url.path
        for suffix in ("/chat/completions", "/models"):
            if path.endswith(suffix):
                path = path[:-len(suffix)]
        if not path and url.hostname in ("localhost", "127.0.0.1", "::1") and port == 11434:
            path = "/v1"
        return urlunsplit((url.scheme, url.netloc, path.rstrip("/"), "", ""))


class ModelConfigResponse(BaseModel):
    id: int
    name: str
    provider: str
    base_url: str
    model: str
    has_api_key: bool
    is_default: bool
