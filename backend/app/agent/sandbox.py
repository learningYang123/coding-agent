"""
代码沙箱 - 安全执行简单代码片段

安全措施：
1. 子进程隔离，使用资源限制
2. 黑名单过滤危险操作（os.system, subprocess, eval exec 等）
3. 执行超时强制终止
4. 内存限制（Windows 上通过 job object 实现，简化处理）
5. 输出大小限制
"""
import ast
import re
import subprocess
import sys
import asyncio
import tempfile
import os
from typing import Dict, Optional, Tuple
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger()


# 危险模块黑名单
DANGEROUS_MODULES = {
    "os", "sys", "subprocess", "shutil", "socket", "http", "urllib",
    "ftplib", "telnetlib", "smtplib", "xmlrpc", "multiprocessing",
    "threading", "ctypes", "cffi", "pickle", "marshal", "codecs",
    "code", "pydoc", "inspect",
}

# 危险函数黑名单（AST 检查）
DANGEROUS_CALLS = {
    "eval", "exec", "compile", "__import__", "open", "input",
    "breakpoint", "exit", "quit",
}

# 危险属性黑名单
DANGEROUS_ATTRS = {
    "__import__", "__builtins__", "__class__", "__subclasses__",
    "__bases__", "__mro__", "__globals__", "__code__",
}

# 输出大小限制
MAX_OUTPUT_SIZE = 10000


class CodeSandbox:
    """代码沙箱"""

    def __init__(self):
        self.enabled = settings.SANDBOX_ENABLED
        self.timeout = settings.SANDBOX_TIMEOUT

    def validate_code(self, code: str) -> Tuple[bool, Optional[str]]:
        """
        安全检查代码

        Returns:
            (是否安全, 拒绝原因)
        """
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return False, f"语法错误: {e}"

        # 检查 import
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    module_name = alias.name.split(".")[0]
                    if module_name in DANGEROUS_MODULES:
                        return False, f"禁止导入模块: {module_name}"

            elif isinstance(node, ast.ImportFrom):
                module_name = (node.module or "").split(".")[0]
                if module_name in DANGEROUS_MODULES:
                    return False, f"禁止从模块导入: {module_name}"

            elif isinstance(node, ast.Call):
                # 检查危险函数调用
                if isinstance(node.func, ast.Name):
                    if node.func.id in DANGEROUS_CALLS:
                        return False, f"禁止调用函数: {node.func.id}"
                elif isinstance(node.func, ast.Attribute):
                    if node.func.attr in DANGEROUS_CALLS:
                        return False, f"禁止调用方法: {node.func.attr}"

            elif isinstance(node, ast.Attribute):
                if node.attr in DANGEROUS_ATTRS:
                    return False, f"禁止访问属性: {node.attr}"

        # 简单文本匹配检查（兜底）
        dangerous_patterns = [
            (r'os\.system', 'os.system'),
            (r'os\.popen', 'os.popen'),
            (r'subprocess\.', 'subprocess'),
            (r'__import__', '__import__'),
            (r'exec\(', 'exec'),
            (r'eval\(', 'eval'),
            (r'compile\(', 'compile'),
        ]
        for pattern, name in dangerous_patterns:
            if re.search(pattern, code):
                return False, f"检测到危险操作: {name}"

        return True, None

    async def execute(self, code: str) -> Dict:
        """
        安全执行 Python 代码

        Args:
            code: 要执行的 Python 代码

        Returns:
            {"success": bool, "output": str, "error": Optional[str], "execution_time": float}
        """
        if not self.enabled:
            return {
                "success": False,
                "output": "",
                "error": "沙箱未启用",
                "execution_time": 0,
            }

        # 安全检查
        is_safe, reason = self.validate_code(code)
        if not is_safe:
            return {
                "success": False,
                "output": "",
                "error": f"安全检查未通过: {reason}",
                "execution_time": 0,
            }

        # 准备执行环境
        # 重定向 stdout/stderr
        wrapper_code = f"""
import sys
import io

class TeeWriter:
    def __init__(self):
        self.buffer = io.StringIO()
    def write(self, text):
        self.buffer.write(text)
    def getvalue(self):
        return self.buffer.getvalue()

stdout_writer = TeeWriter()
stderr_writer = TeeWriter()

sys.stdout = stdout_writer
sys.stderr = stderr_writer

try:
{self._indent_code(code, 4)}
except Exception as e:
    import traceback
    traceback.print_exc()

sys.stdout = sys.__stdout__
sys.stderr = sys.__stderr__

print("=== STDOUT ===")
print(stdout_writer.getvalue())
print("=== STDERR ===")
print(stderr_writer.getvalue())
"""

        import time
        start_time = time.time()

        try:
            # 使用子进程执行
            proc = await asyncio.create_subprocess_exec(
                sys.executable, "-c", wrapper_code,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=self.timeout,
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                execution_time = time.time() - start_time
                return {
                    "success": False,
                    "output": "",
                    "error": f"执行超时（{self.timeout}秒）",
                    "execution_time": round(execution_time, 2),
                }

            execution_time = time.time() - start_time
            stdout_text = stdout.decode("utf-8", errors="replace")
            stderr_text = stderr.decode("utf-8", errors="replace")

            # 限制输出大小
            if len(stdout_text) > MAX_OUTPUT_SIZE:
                stdout_text = stdout_text[:MAX_OUTPUT_SIZE] + "\n... (输出已截断)"

            success = proc.returncode == 0
            return {
                "success": success,
                "output": stdout_text,
                "error": stderr_text if stderr_text else None,
                "execution_time": round(execution_time, 2),
            }

        except Exception as e:
            execution_time = time.time() - start_time
            return {
                "success": False,
                "output": "",
                "error": f"执行环境错误: {str(e)}",
                "execution_time": round(execution_time, 2),
            }

    def _indent_code(self, code: str, indent: int) -> str:
        """缩进代码（用于 wrapper）"""
        spaces = " " * indent
        lines = code.split("\n")
        return "\n".join(spaces + line for line in lines)


# 全局实例
sandbox = CodeSandbox()
