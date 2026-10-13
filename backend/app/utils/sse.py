"""
SSE 流式响应工具 - 定义事件类型和推送方法
事件类型：
  - sources: 检索到的代码来源
  - thinking: Agent 思考过程
  - token: LLM 生成的增量 token
  - agent_step: Agent 工具调用步骤
  - done: 生成结束
  - error: 错误信息
"""
import json
import asyncio
from typing import AsyncGenerator, Optional, Any, Dict, List
from dataclasses import dataclass, field
from enum import Enum


class SSEEventType(str, Enum):
    SOURCES = "sources"
    THINKING = "thinking"
    TOKEN = "token"
    AGENT_STEP = "agent_step"
    DONE = "done"
    ERROR = "error"


@dataclass
class SSEEvent:
    """SSE 事件"""
    event: SSEEventType
    data: Any = None
    id: Optional[str] = None

    def to_sse_format(self) -> str:
        """转换为 SSE 格式字符串"""
        lines = []
        if self.id:
            lines.append(f"id: {self.id}")
        lines.append(f"event: {self.event.value}")

        # data 可以是字符串或 JSON
        if isinstance(self.data, str):
            data_str = self.data
        else:
            data_str = json.dumps(self.data, ensure_ascii=False)

        # SSE 规范：多行 data 需要每行都以 data: 开头
        for line in data_str.split("\n"):
            lines.append(f"data: {line}")
        lines.append("")  # 空行分隔事件

        return "\n".join(lines)


# 便捷创建事件的函数
def make_sources_event(sources: List[Dict]) -> SSEEvent:
    return SSEEvent(event=SSEEventType.SOURCES, data=sources)


def make_thinking_event(content: str) -> SSEEvent:
    return SSEEvent(event=SSEEventType.THINKING, data=content)


def make_token_event(token: str) -> SSEEvent:
    return SSEEvent(event=SSEEventType.TOKEN, data=token)


def make_agent_step_event(step_name: str, step_detail: Any = None) -> SSEEvent:
    return SSEEvent(
        event=SSEEventType.AGENT_STEP,
        data={"step": step_name, "detail": step_detail},
    )


def make_done_event(final_data: Any = None) -> SSEEvent:
    return SSEEvent(event=SSEEventType.DONE, data=final_data)


def make_error_event(error_message: str) -> SSEEvent:
    return SSEEvent(event=SSEEventType.ERROR, data={"message": error_message})


async def event_generator(events: AsyncGenerator[SSEEvent, None]) -> AsyncGenerator[str, None]:
    """将 SSEEvent 异步生成器转换为 SSE 格式字符串生成器"""
    try:
        async for event in events:
            yield event.to_sse_format() + "\n"
    except asyncio.CancelledError:
        # 客户端断开连接
        pass
    except Exception as e:
        import traceback
        error_event = make_error_event(str(e))
        yield error_event.to_sse_format() + "\n"


class SSEBuffer:
    """
    SSE 事件缓冲区 - 用于在不同协程间传递事件
    支持 put/get 操作，put 时会通知等待的消费者
    """

    def __init__(self):
        self._queue: asyncio.Queue = asyncio.Queue()
        self._closed = False

    async def put(self, event: SSEEvent):
        """放入事件"""
        if not self._closed:
            await self._queue.put(event)

    async def put_token(self, token: str):
        """便捷：放入 token 事件"""
        await self.put(make_token_event(token))

    async def put_sources(self, sources: List[Dict]):
        """便捷：放入 sources 事件"""
        await self.put(make_sources_event(sources))

    async def put_thinking(self, content: str):
        """便捷：放入 thinking 事件"""
        await self.put(make_thinking_event(content))

    async def put_agent_step(self, step_name: str, step_detail: Any = None):
        """便捷：放入 agent_step 事件"""
        await self.put(make_agent_step_event(step_name, step_detail))

    async def put_done(self, final_data: Any = None):
        """便捷：放入 done 事件"""
        await self.put(make_done_event(final_data))
        self._closed = True

    async def put_error(self, error_message: str):
        """便捷：放入 error 事件并关闭"""
        await self.put(make_error_event(error_message))
        self._closed = True

    async def get(self) -> Optional[SSEEvent]:
        """获取事件，队列关闭且为空时返回 None"""
        if self._closed and self._queue.empty():
            return None
        return await self._queue.get()

    async def stream(self) -> AsyncGenerator[SSEEvent, None]:
        """作为异步迭代器使用"""
        while True:
            event = await self.get()
            if event is None:
                break
            yield event

    @property
    def is_closed(self) -> bool:
        return self._closed
