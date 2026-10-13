"""
RAG 问答管道 - 整合检索 + 生成
支持两种模式：
  1. normal:  常规 RAG（向量检索 chunks + 文件级兜底）
  2. overview: 项目概览（目录树 + 关键文件采样 + 统计）
"""
from typing import List, Dict, Optional, AsyncGenerator
from app.rag.retriever import retriever
from app.rag.llm_service import llm_service
from app.rag.overview import classify_query, build_repo_overview
from app.core.logging import get_logger
from pathlib import Path
import os

logger = get_logger()


# ========= System Prompt =========

RAG_SYSTEM_PROMPT = """你是一个专业的企业代码智能助手。你的任务是根据提供的代码上下文，回答用户关于业务逻辑和代码实现的问题。

## 回答要求
1. **基于代码事实**：所有回答必须严格基于提供的代码上下文，不要编造或猜测。
2. **代码引用**：引用代码时标注 `文件路径:行号` 格式。
3. **简洁清晰**：用简明扼要的语言解释复杂逻辑。
4. **完整性**：如果上下文不完整，请说明并基于现有信息尽力回答。
5. **语言**：使用中文回答，代码保持原样。"""

OVERVIEW_SYSTEM_PROMPT = """你是一个经验丰富的软件架构师，请根据提供的项目仓库信息，为用户做一份清晰、专业的项目介绍。

## 回答要求
1. **结构化**：按下面的「回答结构模板」组织你的回答。
2. **基于事实**：所有描述必须基于提供的仓库目录树、统计数据和代码文件，不要编造。
3. **中文**：使用中文回答，代码路径保持原样。

## 回答结构模板
请按以下顺序组织内容：

### 1. 项目概览
- 一句话说明这是个什么项目
- 技术栈（根据文件类型 + 依赖文件推断）

### 2. 目录结构
- 展示关键目录的作用（不要把整棵树搬上来，挑重点）
- 例如：`controller/` → 对外接口层，`service/` → 业务逻辑，`mapper/` → 数据访问

### 3. 核心功能模块
按模块列出主要功能，每个模块 1-2 句话说明做什么：
- 模块 A：...
- 模块 B：...

### 4. 关键文件解读
挑 2-4 个代表性文件，说明它们在架构中的位置和作用，**引用文件路径**。

### 5. 项目统计
用简洁数字列出：总文件数、总代码行数、主要编程语言。

### 6. 建议的阅读顺序（如果用户要深入源码）
按推荐文件列表，给出「从哪里开始看 → 接下来看哪里」的路径。"""


# ========= Prompt Template =========

RAG_USER_PROMPT_TEMPLATE = """## 用户问题
{query}

## 代码上下文
{sources_text}

## 请回答
请基于上述代码上下文，回答用户的问题。"""


OVERVIEW_USER_PROMPT_TEMPLATE = """## 用户问题
{query}

## 仓库概览信息

### 目录树（精简）
```
{tree}
```

### 项目统计
```json
{stats}
```

### 关键文件内容（README / 配置 / 入口）
{key_files_text}

### 建议先读的文件
{recommendations_text}

## 请回答
请按照系统提示中的「回答结构模板」，为用户做一份完整的项目介绍。"""


# ========= 格式化函数 =========

def _format_sources_for_prompt(sources: List[Dict]) -> str:
    """常规 RAG: 把 chunks + documents 格式化为 prompt"""
    if not sources:
        return "（未检索到相关代码）"

    chunk_sources = [s for s in sources if s.get("type") != "document"]
    doc_sources = [s for s in sources if s.get("type") == "document"]

    parts = []
    if chunk_sources:
        parts.append("### 精准命中片段（最相关的函数/类）")
        for i, src in enumerate(chunk_sources, 1):
            header = f"#### 片段 {i}"
            if src.get("chunk_name"):
                header += f" - {src['chunk_name']}"
            header += f"\n**文件**: `{src.get('file_path', 'unknown')}`"
            if src.get("start_line") and src.get("end_line"):
                header += f" (L{src['start_line']}-L{src['end_line']})"
            header += f"\n**相关度**: {src.get('score', 0):.3f}"
            content = src.get("content", "")
            parts.append(f"{header}\n\n```\n{content}\n```")

    if doc_sources:
        parts.append("### 相关完整文件（文件级兜底，帮助理解全貌）")
        for i, src in enumerate(doc_sources, 1):
            header = f"#### 文件 {i}"
            header += f"\n**文件**: `{src.get('file_path', 'unknown')}`"
            content = src.get("content", "")
            parts.append(f"{header}\n\n```\n{content}\n```")

    return "\n\n".join(parts)


def _format_overview_for_prompt(overview: Dict) -> Dict[str, str]:
    """把 build_repo_overview 结果格式化为 template 变量"""
    import json

    key_files_parts = []
    for kf in overview.get("key_files", []):
        content = kf.get("content", "")
        if len(content) > 12000:
            content = content[:12000] + "\n# ... (已截断)"
        key_files_parts.append(
            f"#### `{kf['file_path']}`\n\n```\n{content}\n```"
        )
    key_files_text = "\n\n".join(key_files_parts) if key_files_parts else "（未发现 README/配置文件）"

    recs = overview.get("recommendations", [])
    recs_text = "\n".join(f"{i+1}. `{p}`" for i, p in enumerate(recs)) if recs else "（无推荐）"

    stats = overview.get("stats", {})

    return {
        "tree": overview.get("tree", "(空)"),
        "stats": json.dumps(stats, ensure_ascii=False, indent=2),
        "key_files_text": key_files_text,
        "recommendations_text": recs_text,
    }


# ========= Pipeline =========

class RAGPipeline:
    """RAG 问答管道 - 支持 normal + overview 双模式"""

    def __init__(self, llm=None):
        self.retriever = retriever
        self.llm = llm if llm is not None else llm_service

    # ---- 工具 ----

    def _resolve_repo_paths(self, allowed_repo_ids: Optional[List[int]]) -> List[Path]:
        """根据 repo_id 找到本地仓库路径"""
        if not allowed_repo_ids:
            base = Path("./data/repos")
            if not base.exists():
                return []
            return [p for p in base.iterdir() if p.is_dir()]

        paths = []
        base = Path("./data/repos")
        for rid in allowed_repo_ids:
            p = base / f"repo_{rid}"
            if p.exists():
                paths.append(p)
        return paths

    # ---- 常规 RAG ----

    def build_rag_messages(
        self,
        query: str,
        sources: List[Dict],
        history: Optional[List[Dict]] = None,
    ) -> List[Dict]:
        sources_text = _format_sources_for_prompt(sources)
        user_prompt = RAG_USER_PROMPT_TEMPLATE.format(query=query, sources_text=sources_text)
        messages = [{"role": "system", "content": RAG_SYSTEM_PROMPT}]
        if history:
            for msg in history[-6:]:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                if role in ("user", "assistant"):
                    messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": user_prompt})
        return messages

    # ---- 项目概览 ----

    def build_overview_messages(
        self,
        query: str,
        overview_contexts: List[Dict],
        history: Optional[List[Dict]] = None,
    ) -> List[Dict]:
        """
        把多个仓库的 overview 合并成一个 prompt。
        如果只选了一个仓库就给一个仓库的信息；选多个就并列给出。
        """
        if not overview_contexts:
            # 没找到任何仓库，降级成普通 RAG 空结果
            return self.build_rag_messages(query, [], history)

        # 单仓库 → 完整输出
        if len(overview_contexts) == 1:
            ov = overview_contexts[0]
            vars_ = _format_overview_for_prompt(ov)
            user_prompt = OVERVIEW_USER_PROMPT_TEMPLATE.format(
                query=query, **vars_
            )
            messages = [{"role": "system", "content": OVERVIEW_SYSTEM_PROMPT}]
            if history:
                for msg in history[-6:]:
                    role = msg.get("role", "user")
                    content = msg.get("content", "")
                    if role in ("user", "assistant"):
                        messages.append({"role": role, "content": content})
            messages.append({"role": "user", "content": user_prompt})
            return messages

        # 多仓库 → 合并
        combined_parts = []
        combined_tree = []
        combined_key_files = []
        all_stats = []
        all_recs = []

        for ov in overview_contexts:
            combined_parts.append(f"# 仓库: {ov.get('repo_id', 'unknown')}")
            combined_tree.append(ov.get("tree", ""))
            for kf in ov.get("key_files", []):
                combined_key_files.append(f"## {kf['file_path']}\n```\n{kf['content'][:8000]}\n```")
            all_stats.append(ov.get("stats", {}))
            all_recs.extend(ov.get("recommendations", []))

        combined_user = f"""## 用户问题
{query}

你选择了多个仓库。下面是它们的概览信息。

{'---\n'.join(combined_key_files)}

请分别介绍每个仓库，或者综合起来给一份总览（如果它们有关联的话）。"""

        messages = [{"role": "system", "content": OVERVIEW_SYSTEM_PROMPT}]
        if history:
            for msg in history[-6:]:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                if role in ("user", "assistant"):
                    messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": combined_user})
        return messages

    # ---- 统一入口 ----

    async def answer(
        self,
        query: str,
        allowed_repo_ids: Optional[List[int]] = None,
        history: Optional[List[Dict]] = None,
    ) -> Dict:
        """同步问答"""
        mode = classify_query(query)
        logger.info(f"Query 分类: mode={mode}, query={query[:50]}")

        if mode == "overview":
            paths = self._resolve_repo_paths(allowed_repo_ids)
            if not paths:
                # 没选仓库 → 降级成正常 RAG 告诉用户要先选
                sources = self.retriever.retrieve(query, allowed_repo_ids)
                messages = self.build_rag_messages(query, sources, history)
                answer = await self.llm.chat(messages, stream=False)
                return {"answer": answer, "sources": sources, "mode": "normal"}

            overview_contexts = []
            for p in paths:
                ov = build_repo_overview(p)
                ov["repo_id"] = p.name  # 给个标识
                overview_contexts.append(ov)

            messages = self.build_overview_messages(query, overview_contexts, history)
            answer = await self.llm.chat(messages, stream=False)

            # 把 overview 信息也塞进 sources 里（前端可以展示）
            overview_sources = []
            for ov, rp in zip(overview_contexts, paths):
                overview_sources.append({
                    "type": "overview",
                    "file_path": str(rp),
                    "content": ov.get("tree", ""),
                    "stats": ov.get("stats", {}),
                    "recommendations": ov.get("recommendations", []),
                    "score": 1.0,
                })

            return {"answer": answer, "sources": overview_sources, "mode": "overview"}

        # normal
        sources = self.retriever.retrieve(query, allowed_repo_ids)
        messages = self.build_rag_messages(query, sources, history)
        answer = await self.llm.chat(messages, stream=False)
        return {"answer": answer, "sources": sources, "mode": "normal"}

    async def stream_answer(
        self,
        query: str,
        allowed_repo_ids: Optional[List[int]] = None,
        history: Optional[List[Dict]] = None,
    ) -> AsyncGenerator[Dict, None]:
        """流式问答"""
        mode = classify_query(query)
        logger.info(f"Query 分类: mode={mode}, query={query[:50]}")

        if mode == "overview":
            paths = self._resolve_repo_paths(allowed_repo_ids)
            if not paths:
                sources = self.retriever.retrieve(query, allowed_repo_ids)
                messages = self.build_rag_messages(query, sources, history)
                yield {"type": "sources", "data": sources}
                full = ""
                async for token in self.llm.chat(messages, stream=True):
                    full += token
                    yield {"type": "token", "data": token}
                yield {"type": "done", "data": {"answer": full, "sources": sources, "mode": "normal"}}
                return

            overview_contexts = []
            for p in paths:
                ov = build_repo_overview(p)
                ov["repo_id"] = p.name
                overview_contexts.append(ov)

            overview_sources = []
            for ov, rp in zip(overview_contexts, paths):
                overview_sources.append({
                    "type": "overview",
                    "file_path": str(rp),
                    "content": ov.get("tree", ""),
                    "stats": ov.get("stats", {}),
                    "recommendations": ov.get("recommendations", []),
                    "score": 1.0,
                })

            yield {"type": "sources", "data": overview_sources}

            messages = self.build_overview_messages(query, overview_contexts, history)

            full = ""
            async for token in self.llm.chat(messages, stream=True):
                full += token
                yield {"type": "token", "data": token}
            yield {"type": "done", "data": {"answer": full, "sources": overview_sources, "mode": "overview"}}
            return

        # normal
        sources = self.retriever.retrieve(query, allowed_repo_ids)
        yield {"type": "sources", "data": sources}
        messages = self.build_rag_messages(query, sources, history)
        full = ""
        async for token in self.llm.chat(messages, stream=True):
            full += token
            yield {"type": "token", "data": token}
        yield {"type": "done", "data": {"answer": full, "sources": sources, "mode": "normal"}}


# 全局实例
rag_pipeline = RAGPipeline()
