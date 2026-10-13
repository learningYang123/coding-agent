"""
Agent 工具定义 - 供 LangGraph Agent 调用的工具集
"""
import re
import traceback
from typing import List, Dict, Optional
from app.core.logging import get_logger
from app.rag.retriever import retriever
from app.agent.sandbox import sandbox

logger = get_logger()


class AgentTools:
    """Agent 可用工具集"""

    @staticmethod
    def search_code(query: str, repo_ids: Optional[List[int]] = None, top_k: int = 5) -> List[Dict]:
        """
        搜索代码库中的相关代码片段

        Args:
            query: 搜索查询（描述你想找到的代码功能或逻辑）
            repo_ids: 限定搜索的仓库 ID 列表，None 表示搜索所有可访问仓库
            top_k: 返回结果数量

        Returns:
            相关代码片段列表
        """
        results = retriever.retrieve(query, allowed_repo_ids=repo_ids, top_k=top_k)
        # 精简返回，只保留关键字段
        return [
            {
                "file_path": r.get("file_path"),
                "chunk_name": r.get("chunk_name"),
                "chunk_type": r.get("chunk_type"),
                "start_line": r.get("start_line"),
                "end_line": r.get("end_line"),
                "score": r.get("score"),
                "content": r.get("content", "")[:1500],  # 限制大小
            }
            for r in results
        ]

    @staticmethod
    async def run_code(code: str) -> Dict:
        """
        在安全沙箱中执行 Python 代码片段

        安全限制：
        - 禁止文件操作、网络请求、子进程
        - 执行超时 30 秒
        - 仅支持标准库中的安全模块

        Args:
            code: 要执行的 Python 代码

        Returns:
            执行结果，包含 success, output, error, execution_time
        """
        return await sandbox.execute(code)

    @staticmethod
    def analyze_error_log(error_log: str) -> Dict:
        """
        分析错误日志，提取关键信息

        Args:
            error_log: 完整的错误堆栈或异常日志

        Returns:
            解析结果，包含 error_type, error_message, file_location, suggestion
        """
        result = {
            "error_type": None,
            "error_message": None,
            "file_location": None,
            "line_number": None,
            "stack_frames": [],
            "suggestion": "",
        }

        if not error_log:
            result["suggestion"] = "未提供错误日志"
            return result

        # 提取异常类型和消息
        # 匹配 "ErrorType: message" 格式
        error_pattern = re.compile(
            r'(?:Traceback \(most recent call last\):\s*\n(?:\s*File[^)]+\)\s*,?\s*line\s+\d+[^\n]*\n\s*[^\n]+\n)*\s*(?:[A-Z][a-zA-Z]+(?:Error|Exception|Warning)):\s*(.*?))',
            re.MULTILINE,
        )
        simple_pattern = re.compile(r'([A-Z][a-zA-Z]+(?:Error|Exception|Warning))[:：]\s*(.+)')

        # 提取堆栈帧
        frame_pattern = re.compile(
            r'File\s+"([^"]+)",\s*line\s+(\d+)(?:,\s*in\s+(\w+))?'
        )

        frames = frame_pattern.findall(error_log)
        for file_path, line_num, func_name in frames:
            result["stack_frames"].append({
                "file": file_path,
                "line": int(line_num),
                "function": func_name,
            })

        if frames:
            # 最后一个帧通常是错误发生位置
            last_frame = frames[-1]
            result["file_location"] = last_frame[0]
            result["line_number"] = int(last_frame[1])

        # 匹配异常类型
        traceback_match = error_pattern.search(error_log)
        simple_match = simple_pattern.search(error_log)

        if traceback_match:
            # 从最后一行提取
            lines = error_log.strip().split("\n")
            for line in reversed(lines):
                if ":" in line:
                    parts = line.split(":", 1)
                    if re.match(r'^[A-Z][a-zA-Z]+(?:Error|Exception|Warning)$', parts[0].strip()):
                        result["error_type"] = parts[0].strip()
                        result["error_message"] = parts[1].strip()
                        break
        elif simple_match:
            result["error_type"] = simple_match.group(1)
            result["error_message"] = simple_match.group(2).strip()

        # 生成建议
        if result["error_type"]:
            result["suggestion"] = f"检测到 {result['error_type']}"
            if result["file_location"]:
                result["suggestion"] += f"，发生位置: {result['file_location']}:{result['line_number']}"
            if result["error_message"]:
                result["suggestion"] += f"\n错误信息: {result['error_message']}"

        return result


# 全局实例
agent_tools = AgentTools()
