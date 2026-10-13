"""
代码解析器 - 使用 tree-sitter 进行语义分块
确保函数、类不被拆分
"""
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from pathlib import Path
import re

from app.core.logging import get_logger

logger = get_logger()


@dataclass
class CodeChunkInfo:
    """代码分块信息"""
    content: str
    chunk_type: str  # function / class / method / text
    chunk_name: Optional[str] = None
    start_line: int = 0
    end_line: int = 0
    language: str = ""


# tree-sitter 语言映射
LANGUAGE_MAP = {
    ".py": "python",
    ".java": "java",
    ".js": "javascript",
    ".ts": "typescript",
    ".jsx": "javascript",
    ".tsx": "typescript",
    ".go": "go",
    ".rs": "rust",
    ".c": "c",
    ".cpp": "cpp",
    ".h": "c",
    ".hpp": "cpp",
    ".md": "markdown",
    ".txt": "text",
}

CODE_EXTENSIONS = {".py", ".java", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs", ".c", ".cpp", ".h", ".hpp"}
DOC_EXTENSIONS = {".md", ".markdown", ".txt"}


class TreeSitterParser:
    """使用 tree-sitter 解析代码"""

    def __init__(self):
        self._parsers = {}
        self._languages = {}
        self._initialized = False
        self._try_init()

    def _try_init(self):
        """尝试初始化 tree-sitter"""
        try:
            import tree_sitter
            from tree_sitter_languages import get_language, get_parser

            self._ts = tree_sitter
            self._get_language = get_language
            self._get_parser = get_parser
            self._initialized = True
            logger.info("tree-sitter 初始化成功")
        except Exception as e:
            logger.warning(f"tree-sitter 初始化失败，将使用回退解析方案: {e}")
            self._initialized = False

    def parse_code(self, code: str, language: str) -> List[CodeChunkInfo]:
        """
        解析代码为语义分块
        优先使用 tree-sitter，失败则回退到正则解析
        """
        if self._initialized and language in ("python", "java", "javascript", "typescript"):
            try:
                return self._parse_with_tree_sitter(code, language)
            except Exception as e:
                logger.warning(f"tree-sitter 解析失败，回退到正则: {e}")

        # 回退方案
        return self._parse_with_regex(code, language)

    def _parse_with_tree_sitter(self, code: str, language: str) -> List[CodeChunkInfo]:
        """使用 tree-sitter 解析"""
        parser = self._get_parser(language)
        tree = parser.parse(code.encode("utf-8"))

        chunks: List[CodeChunkInfo] = []
        self._walk_tree(tree.root_node, code, chunks, language)

        # 如果 tree-sitter 没有找到任何有意义的节点，回退
        meaningful = [c for c in chunks if c.chunk_type in ("function", "class", "method")]
        if not meaningful:
            return self._parse_with_regex(code, language)

        return chunks

    def _walk_tree(self, node, code: str, chunks: List[CodeChunkInfo], language: str):
        """遍历语法树"""
        # 关注的节点类型
        target_types = {
            "python": {"function_definition", "class_definition", "decorated_definition"},
            "java": {"method_declaration", "class_declaration", "interface_declaration", "constructor_declaration"},
            "javascript": {"function_declaration", "class_declaration", "method_definition", "arrow_function", "function_expression"},
            "typescript": {"function_declaration", "class_declaration", "method_definition", "arrow_function"},
        }

        interesting = target_types.get(language, set())

        if node.type in interesting:
            start_point = node.start_point
            end_point = node.end_point
            content = code[node.start_byte:node.end_byte]

            # 尝试提取名称
            name = self._extract_name(node, code)

            chunk_type = "function"
            if "class" in node.type:
                chunk_type = "class"
            elif "method" in node.type or "constructor" in node.type:
                chunk_type = "method"

            chunks.append(CodeChunkInfo(
                content=content,
                chunk_type=chunk_type,
                chunk_name=name,
                start_line=start_point[0] + 1,
                end_line=end_point[0] + 1,
                language=language,
            ))
            return  # 不再深入子节点

        # 递归遍历子节点
        for child in node.children:
            self._walk_tree(child, code, chunks, language)

    def _extract_name(self, node, code: str) -> Optional[str]:
        """尝试从节点中提取名称"""
        for child in node.children:
            if child.type in ("identifier", "name", "property_identifier"):
                return code[child.start_byte:child.end_byte]
        # 尝试找到第一个 identifier 后代
        def find_id(n):
            if n.type in ("identifier", "name"):
                return code[n.start_byte:n.end_byte]
            for c in n.children:
                result = find_id(c)
                if result:
                    return result
            return None
        return find_id(node)

    def _parse_with_regex(self, code: str, language: str) -> List[CodeChunkInfo]:
        """正则回退解析"""
        chunks: List[CodeChunkInfo] = []
        lines = code.split("\n")

        if language == "python":
            # 匹配 def 和 class
            pattern = re.compile(r"^(\s*)(def|class)\s+(\w+)")
        elif language == "java":
            pattern = re.compile(r"^(public|private|protected|static|\s)*(class|interface|enum|void|\w+)\s+(\w+)")
        elif language in ("javascript", "typescript"):
            pattern = re.compile(r"^(const|let|var|function|class|export)\s+(\w+|\{)")
        else:
            # 通用匹配：基于行长度和空白
            return self._parse_by_lines(code, language)

        current_start = 0
        current_name = None
        current_type = None

        for i, line in enumerate(lines):
            match = pattern.match(line)
            if match:
                # 保存上一个块
                if current_name is not None:
                    chunk_content = "\n".join(lines[current_start:i]).strip()
                    if chunk_content:
                        chunks.append(CodeChunkInfo(
                            content=chunk_content,
                            chunk_type=current_type or "text",
                            chunk_name=current_name,
                            start_line=current_start + 1,
                            end_line=i,
                            language=language,
                        ))

                current_name = match.group(match.lastindex or 1)  # type: ignore
                current_start = i
                keyword = match.group(2) if match.lastindex and match.lastindex >= 2 else ""
                current_type = "class" if "class" in keyword else "function"

        # 最后一个块
        if current_name is not None:
            chunk_content = "\n".join(lines[current_start:]).strip()
            if chunk_content:
                chunks.append(CodeChunkInfo(
                    content=chunk_content,
                    chunk_type=current_type or "text",
                    chunk_name=current_name,
                    start_line=current_start + 1,
                    end_line=len(lines),
                    language=language,
                ))

        # 如果没有匹配到任何结构，回退到按行分块
        if not chunks:
            return self._parse_by_lines(code, language)

        return chunks

    def _parse_by_lines(self, code: str, language: str, max_lines: int = 60) -> List[CodeChunkInfo]:
        """按行数分块（最终回退）"""
        chunks = []
        lines = code.split("\n")

        for i in range(0, len(lines), max_lines):
            chunk_lines = lines[i:i + max_lines]
            content = "\n".join(chunk_lines).strip()
            if content:
                chunks.append(CodeChunkInfo(
                    content=content,
                    chunk_type="text",
                    start_line=i + 1,
                    end_line=i + len(chunk_lines),
                    language=language,
                ))

        return chunks


class TextSplitter:
    """文档文本分块器"""

    def __init__(self, max_size: int = 1500, overlap: int = 200):
        self.max_size = max_size
        self.overlap = overlap

    def split_text(self, text: str) -> List[CodeChunkInfo]:
        """按 token/字符数分割纯文本（如 Markdown）"""
        if not text.strip():
            return []

        chunks = []
        lines = text.split("\n")
        current_lines = []
        current_size = 0

        for line in lines:
            line_size = len(line) + 1  # +1 for newline
            if current_size + line_size > self.max_size and current_lines:
                # 保存当前块
                chunk_text = "\n".join(current_lines).strip()
                if chunk_text:
                    chunks.append(CodeChunkInfo(
                        content=chunk_text,
                        chunk_type="text",
                        start_line=len(chunks) * 100 + 1,
                        end_line=len(chunks) * 100 + len(current_lines),
                        language="markdown",
                    ))

                # 保留 overlap 行
                if self.overlap > 0:
                    overlap_lines = current_lines[-max(1, self.overlap // 20):]
                    current_lines = overlap_lines + [line]
                    current_size = sum(len(l) + 1 for l in overlap_lines) + line_size
                else:
                    current_lines = [line]
                    current_size = line_size
            else:
                current_lines.append(line)
                current_size += line_size

        # 最后一个块
        if current_lines:
            chunk_text = "\n".join(current_lines).strip()
            if chunk_text:
                chunks.append(CodeChunkInfo(
                    content=chunk_text,
                    chunk_type="text",
                    start_line=len(chunks) * 100 + 1,
                    end_line=len(chunks) * 100 + len(current_lines),
                    language="markdown",
                ))

        return chunks


# 全局实例
_parser = TreeSitterParser()
_text_splitter = TextSplitter()


def parse_file(file_path: str, content: str) -> List[CodeChunkInfo]:
    """
    解析单个文件为代码分块列表

    Args:
        file_path: 文件路径（用于判断语言）
        content: 文件内容

    Returns:
        CodeChunkInfo 列表
    """
    path = Path(file_path)
    suffix = path.suffix.lower()
    language = LANGUAGE_MAP.get(suffix, "text")

    if suffix in CODE_EXTENSIONS:
        return _parser.parse_code(content, language)
    elif suffix in DOC_EXTENSIONS:
        return _text_splitter.split_text(content)
    else:
        # 未知类型，尝试作为代码解析
        return _text_splitter.split_text(content)
