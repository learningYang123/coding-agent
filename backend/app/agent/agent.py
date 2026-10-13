"""
LangGraph Agent - 支持任务规划、工具调用、代码执行的智能助手

流程：
1. 用户输入问题 / 报错日志
2. Planner 分析任务，决定是否需要调用工具
3. 执行阶段：调用工具（代码搜索 / 沙箱执行 / 错误分析）
4. 汇总结果，生成最终回答
"""
from typing import List, Dict, Optional, AsyncGenerator, Any
from datetime import datetime

from app.core.config import settings
from app.core.logging import get_logger
from app.rag.llm_service import llm_service
from app.agent.tools import agent_tools

logger = get_logger()


# Agent System Prompt
AGENT_SYSTEM_PROMPT = """你是一个企业代码智能诊断 Agent。你可以使用以下工具来帮助用户：

## 可用工具

1. **search_code(query, repo_ids?, top_k?)** - 搜索代码库
   - 根据功能描述或错误关键词查找相关代码片段
   - 返回文件路径、行号、代码内容

2. **run_code(code)** - 在安全沙箱中执行 Python 代码
   - 验证逻辑、调试算法、运行测试用例
   - 禁止网络、文件、子进程操作

3. **analyze_error_log(error_log)** - 解析错误堆栈
   - 提取异常类型、错误消息、堆栈位置
   - 帮助定位问题根源

## 工作流程

### 对于业务逻辑问答
1. 使用 search_code 搜索相关代码
2. 阅读代码，理解逻辑
3. 用清晰的语言解释给用户

### 对于报错日志排错
1. 使用 analyze_error_log 解析日志结构
2. 使用 search_code 搜索错误位置的代码
3. 分析可能的原因
4. 如果可能，用 run_code 验证修复方案
5. 给出修复建议和代码示例

## 回答要求
- 中文回答
- 引用代码时标注文件路径和行号
- 如果无法确定根因，说明可能的原因并给出排查方向
- 保持简洁，重点突出"""


class CodeAgent:
    """代码智能 Agent"""

    def __init__(self, llm=None):
        self.llm = llm if llm is not None else llm_service
        self.tools = agent_tools

    async def run(
        self,
        query: str,
        error_log: Optional[str] = None,
        allowed_repo_ids: Optional[List[int]] = None,
    ) -> Dict:
        """
        同步执行 Agent（内部会逐步调用工具）

        Returns:
            {"answer": str, "thinking": str, "sources": List[Dict]}
        """
        thinking_parts = []
        all_sources = []
        error_info = None

        # 第一步：分析输入，搜索相关代码
        thinking_parts.append(f"📋 分析用户输入...")

        combined_query = query
        if error_log:
            # 先分析错误日志
            thinking_parts.append(f"🔍 解析错误日志...")
            error_info = self.tools.analyze_error_log(error_log)
            thinking_parts.append(f"  -> 识别到: {error_info.get('error_type') or '未知错误'}")
            if error_info.get("file_location"):
                thinking_parts.append(f"  -> 位置: {error_info['file_location']}:{error_info['line_number']}")
            combined_query = f"{query}\n\n错误堆栈关键信息:\n类型: {error_info.get('error_type')}\n位置: {error_info.get('file_location')}\n消息: {error_info.get('error_message')}"

            # 基于错误信息搜索代码
            search_query = error_info.get("error_message") or query
            if error_info.get("file_location"):
                file_name = error_info["file_location"].split("/")[-1].split("\\")[-1]
                search_query = f"{file_name} {search_query}"

            thinking_parts.append(f"🔎 搜索相关代码: '{search_query[:80]}'...")
            code_results = self.tools.search_code(search_query, allowed_repo_ids, top_k=6)
            all_sources.extend(code_results)
            thinking_parts.append(f"  -> 找到 {len(code_results)} 个相关片段")
        else:
            thinking_parts.append(f"🔎 搜索相关代码: '{query[:80]}'...")
            code_results = self.tools.search_code(query, allowed_repo_ids, top_k=6)
            all_sources.extend(code_results)
            thinking_parts.append(f"  -> 找到 {len(code_results)} 个相关片段")

        # 构建 LLM 消息
        messages = self._build_messages(
            query=query,
            error_log=error_log,
            error_info=error_info if error_log else None,
            code_results=all_sources,
            thinking=thinking_parts,
        )

        # 生成回答
        thinking_parts.append(f"✍️ 生成回答...")
        answer = await self.llm.chat(messages, stream=False)

        return {
            "answer": answer,
            "thinking": "\n".join(thinking_parts),
            "sources": all_sources,
        }

    async def stream_run(
        self,
        query: str,
        error_log: Optional[str] = None,
        allowed_repo_ids: Optional[List[int]] = None,
    ) -> AsyncGenerator[Dict, None]:
        """
        流式执行 Agent - 逐步推送事件

        Yields:
            {"type": "thinking"|"agent_step"|"sources"|"token"|"done", "data": ...}
        """
        all_sources = []

        # === 阶段 1: 分析输入 ===
        yield {"type": "thinking", "data": "📋 分析用户输入..."}

        error_info = None
        combined_query = query

        if error_log:
            yield {"type": "agent_step", "data": {"step": "analyze_error", "detail": "解析错误堆栈"}}
            error_info = self.tools.analyze_error_log(error_log)

            err_type = error_info.get("error_type") or "未知错误"
            yield {"type": "thinking", "data": f"  -> 识别到: {err_type}"}
            if error_info.get("file_location"):
                loc = f"{error_info['file_location']}:{error_info['line_number']}"
                yield {"type": "thinking", "data": f"  -> 位置: {loc}"}

            # 构建搜索查询
            search_query = error_info.get("error_message") or query
            if error_info.get("file_location"):
                file_name = error_info["file_location"].split("/")[-1].split("\\")[-1]
                search_query = f"{file_name} {search_query}"
            combined_query = f"{query} {error_info.get('error_message', '')}"

        # === 阶段 2: 搜索代码 ===
        yield {"type": "agent_step", "data": {"step": "search_code", "detail": f"搜索: '{combined_query[:80]}'"}}

        code_results = self.tools.search_code(combined_query, allowed_repo_ids, top_k=6)
        all_sources.extend(code_results)

        yield {"type": "thinking", "data": f"  -> 找到 {len(code_results)} 个相关片段"}

        # 推送 sources 事件
        yield {"type": "sources", "data": all_sources}

        # === 阶段 3: 构建消息并流式生成 ===
        messages = self._build_messages(
            query=query,
            error_log=error_log,
            error_info=error_info,
            code_results=all_sources,
            thinking=[],
        )

        yield {"type": "agent_step", "data": {"step": "generate", "detail": "生成回答"}}

        full_answer = ""
        async for token in self.llm.chat(messages, stream=True):
            full_answer += token
            yield {"type": "token", "data": token}

        yield {"type": "done", "data": {"answer": full_answer, "sources": all_sources}}

    def _build_messages(
        self,
        query: str,
        error_log: Optional[str],
        error_info: Optional[Dict],
        code_results: List[Dict],
        thinking: List[str],
    ) -> List[Dict]:
        """构建 Agent 消息"""
        user_content_parts = []

        # 原始问题
        user_content_parts.append(f"## 用户问题\n{query}")

        # 错误日志
        if error_log:
            user_content_parts.append(f"## 错误日志\n```\n{error_log[:3000]}\n```")

        # 分析结果
        if error_info:
            info_parts = []
            if error_info.get("error_type"):
                info_parts.append(f"- 异常类型: {error_info['error_type']}")
            if error_info.get("error_message"):
                info_parts.append(f"- 错误消息: {error_info['error_message']}")
            if error_info.get("file_location"):
                info_parts.append(f"- 发生位置: {error_info['file_location']}:{error_info['line_number']}")
            if info_parts:
                user_content_parts.append("## 错误分析\n" + "\n".join(info_parts))

        # 搜索到的代码
        if code_results:
            source_parts = []
            for i, src in enumerate(code_results, 1):
                header = f"### 代码片段 {i}"
                if src.get("chunk_name"):
                    header += f" - {src['chunk_name']}"
                header += f"\n**文件**: `{src.get('file_path', 'unknown')}`"
                if src.get("start_line"):
                    header += f" (L{src['start_line']})"
                content = src.get("content", "")[:2000]
                source_parts.append(f"{header}\n\n```\n{content}\n```")
            user_content_parts.append("## 相关代码\n\n" + "\n\n".join(source_parts))

        messages = [
            {"role": "system", "content": AGENT_SYSTEM_PROMPT},
            {"role": "user", "content": "\n\n".join(user_content_parts)},
        ]

        return messages


# 全局实例
code_agent = CodeAgent()
