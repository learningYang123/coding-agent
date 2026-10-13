"""项目介绍意图识别 + 仓库概览上下文构建"""
import re
from typing import List, Dict, Optional
from dataclasses import dataclass


# ========= 1. 意图识别 =========

# "项目介绍" 类 query 的关键词模式
OVERVIEW_PATTERNS = [
    r'(请)?(介绍|讲解|说明|分析|聊聊|谈谈|讲一讲)',
    r'(整个|全部|这个|那个)?(项目|工程|系统|仓库|代码库|应用)',
    r'(的)?(整体|全貌|概览|架构|结构|组成|功能|模块|设计|实现)',
    r'(项目|系统|工程)?(有哪些|包含哪些|包括什么)',
    r'(项目|仓库|这个)(怎么|如何)(实现|工作|运行)',
    r'(项目|仓库)(介绍|概览|分析|评审|汇报)',
    r'project\s*(overview|summary|architecture|structure)',
    r'(代码|项目)(架构|结构|设计|分析|讲解)',
    r'(详细|深入|全面)(介绍|讲解|分析|了解)',
    r'技术栈',
    r'(技术栈|使用了|用了|用什么)',
]

OVERVIEW_PATTERN = re.compile('|'.join(OVERVIEW_PATTERNS), re.IGNORECASE)


def is_overview_query(query: str) -> bool:
    """判断是否为项目介绍/概览类查询"""
    if not query or len(query) < 3:
        return False
    match = OVERVIEW_PATTERN.search(query)
    # 关键词必须命中 + query 不能太具体（不包含文件名/行号/具体函数名）
    has_specific_target = bool(re.search(r'(?i)\.(java|py|js|ts|go|rs|cpp|c)\b|\b(L\d+|line\s*\d+)', query))
    if has_specific_target:
        return False
    return bool(match)


def classify_query(query: str) -> str:
    """
    Query 分类：
    - overview:  项目介绍/概览 → 走目录树 + 关键文件采样
    - normal:    正常 RAG → 走向量检索
    """
    if is_overview_query(query):
        return "overview"
    return "normal"


# ========= 2. 仓库概览上下文构建 =========

import os
from pathlib import Path
from collections import defaultdict


def build_repo_overview(repo_path: Path, max_files_per_dir: int = 5) -> Dict:
    """
    扫描仓库生成概览信息

    Returns:
        {
            "tree": "...",           # 目录树（精简版）
            "stats": {...},          # 统计：文件数/语言分布/行数
            "key_files": [...],      # 关键文件内容（README/配置/入口）
            "recommendations": [...],# 建议阅读的文件路径
        }
    """
    repo_path = Path(repo_path)
    if not repo_path.exists():
        return {"tree": "", "stats": {}, "key_files": [], "recommendations": []}

    skip_dirs = {
        ".git", "node_modules", "__pycache__", ".idea", ".vscode",
        "dist", "build", "target", ".next", ".venv", "venv", "out",
        ".cache", ".pytest_cache", ".mypy_cache",
    }

    skip_exts = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg",
                 ".woff", ".woff2", ".ttf", ".eot", ".mp3", ".mp4",
                 ".class", ".jar", ".war", ".exe", ".dll", ".so"}

    tree_lines = []
    file_stats: Dict[str, int] = defaultdict(int)
    lang_stats: Dict[str, int] = defaultdict(int)
    total_lines = 0
    key_files = []
    recommendations = []

    # 关键文件路径关键词（命中则全文采样）
    KEY_FILE_PATTERNS = [
        "README", "readme", "pom.xml", "package.json",
        "requirements.txt", "setup.py", "pyproject.toml",
        "build.gradle", "build.gradle.kts", "Makefile",
        "docker-compose", "Dockerfile", ".gitignore",
        "application.yml", "application.yaml", "application.properties",
        "settings.gradle", "tsconfig.json", "vite.config",
    ]

    # 第一遍：遍历
    all_files = []
    for root, dirs, filenames in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        rel_root = Path(root).relative_to(repo_path)

        for fname in filenames:
            fpath = Path(root) / fname
            suffix = fpath.suffix.lower()
            if suffix in skip_exts:
                continue

            rel_path = str(fpath.relative_to(repo_path))
            all_files.append((rel_root, fname, fpath, rel_path))

            # 统计
            if suffix:
                file_stats[suffix] += 1
            # 行数统计
            try:
                with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                    lines = len(f.readlines())
                    total_lines += lines
                    if suffix in (".py", ".java", ".js", ".ts", ".go", ".rs"):
                        lang_stats[suffix.lstrip(".")] += lines
            except Exception:
                pass

            # 关键文件（按路径关键词）
            is_key = False
            rel_path_lower = rel_path.lower()
            for kp in KEY_FILE_PATTERNS:
                if kp in rel_path_lower:
                    is_key = True
                    break

            if is_key:
                try:
                    content = fpath.read_text(encoding="utf-8", errors="ignore")
                    if len(content) > 15000:
                        content = content[:15000] + "\n# ... (截断)"
                    key_files.append({
                        "file_path": rel_path,
                        "content": content,
                    })
                except Exception:
                    pass

    # 生成精简目录树（只到 2 层深度 + 每个目录最多 N 个文件）
    tree_lines.append(f"{repo_path.name}/")
    _build_tree(repo_path, repo_path, tree_lines, depth=0, max_depth=2,
                max_files_per_dir=max_files_per_dir, skip_dirs=skip_dirs, skip_exts=skip_exts)

    # 推荐阅读的文件（按语言 + 入口特征）
    recommendations = _pick_recommended_files(all_files, lang_stats)

    return {
        "tree": "\n".join(tree_lines),
        "stats": {
            "total_files": sum(file_stats.values()),
            "total_lines": total_lines,
            "file_type_distribution": dict(sorted(file_stats.items(), key=lambda x: -x[1])[:10]),
            "language_lines": dict(sorted(lang_stats.items(), key=lambda x: -x[1])[:5]),
        },
        "key_files": key_files,
        "recommendations": recommendations,
    }


def _build_tree(
    root: Path,
    current: Path,
    lines: List[str],
    depth: int,
    max_depth: int,
    max_files_per_dir: int,
    skip_dirs: set,
    skip_exts: set,
):
    """递归构建目录树（精简版）"""
    if depth >= max_depth:
        return

    try:
        entries = sorted(current.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    except PermissionError:
        return

    dirs = [e for e in entries if e.is_dir() and e.name not in skip_dirs]
    files = [e for e in entries if e.is_file() and e.suffix.lower() not in skip_exts]
    files = files[:max_files_per_dir]  # 每个目录只显示前 N 个文件
    if len(entries) - len(dirs) - len(skip_dirs) - len(files) > 0:
        # 还有更多被过滤的文件
        pass

    for fname in files:
        lines.append(f"{'  ' * (depth + 1)}{fname.name}")

    for d in dirs:
        lines.append(f"{'  ' * (depth + 1)}{d.name}/")
        _build_tree(root, d, lines, depth + 1, max_depth, max_files_per_dir, skip_dirs, skip_exts)


def _pick_recommended_files(
    all_files: List,
    lang_stats: Dict[str, int],
    limit: int = 6,
) -> List[str]:
    """
    根据语言分布 + 文件名特征挑推荐文件
    - README 类
    - 入口文件（main/index/app）
    - Controller / Service / Config
    - 平均分布到不同包
    """
    scored = []
    for rel_root, fname, fpath, rel_path in all_files:
        score = 0
        name_lower = fname.lower()
        path_lower = rel_path.lower()

        if "readme" in name_lower:
            score += 100
        if "main" in name_lower or "index" in name_lower or "app." in name_lower:
            score += 80
        if "controller" in path_lower or "rest" in path_lower:
            score += 60
        if "service" in path_lower or "impl" in path_lower:
            score += 50
        if "config" in path_lower:
            score += 40
        if "entity" in path_lower or "model" in path_lower:
            score += 30
        if "mapper" in path_lower or "repository" in path_lower:
            score += 30
        if "dto" in path_lower:
            score += 25
        if fname.startswith("."):
            score -= 50
        if len(rel_path.split("\\")) > 5:
            score -= 10  # 太深的目录降权

        if score > 0:
            scored.append((rel_path, score))

    scored.sort(key=lambda x: -x[1])
    seen_packages = set()
    result = []
    for rel_path, score in scored:
        package = rel_path.split("\\")[0]
        if package not in seen_packages or score > 70:
            result.append(rel_path)
            seen_packages.add(package)
        if len(result) >= limit:
            break

    return result
