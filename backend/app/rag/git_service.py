"""
Git 仓库管理服务 - 克隆仓库、解析文件、入库
"""
import os
import asyncio
import shutil
import subprocess
from pathlib import Path
from typing import Optional, List, Dict
from datetime import datetime

from app.core.config import settings
from app.core.logging import get_logger
from app.rag.code_parser import parse_file, LANGUAGE_MAP, CODE_EXTENSIONS, DOC_EXTENSIONS, CodeChunkInfo
from app.rag.embeddings import embedding_manager
from app.rag.vector_store import faiss_store

logger = get_logger()


class GitService:
    """Git 仓库管理"""

    def __init__(self):
        self.repos_base_path = Path("./data/repos")
        self.repos_base_path.mkdir(parents=True, exist_ok=True)

    async def _run_git(
        self,
        *args: str,
        cwd: Optional[str] = None,
        timeout: Optional[int] = None,
    ) -> subprocess.CompletedProcess:
        """
        在线程池里跑 git 命令，绕开 Windows 下 asyncio.create_subprocess_exec 偶发的
        NotImplementedError（与 uvicorn reload 子进程的事件循环策略有关）。
        """
        cmd = [settings.GIT_EXECUTABLE, *args]
        logger.info(f"执行: {' '.join(cmd)} (cwd={cwd})")

        def _do():
            return subprocess.run(
                cmd,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout,
                encoding="utf-8",
                errors="replace",
            )

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _do)

    async def clone_or_update(
        self,
        repo_id: int,
        git_url: Optional[str] = None,
        local_path: Optional[str] = None,
        branch: str = "main",
    ) -> Path:
        """
        克隆或更新 Git 仓库

        Args:
            repo_id: 仓库 ID
            git_url: Git 远程地址
            local_path: 本地路径（优先使用）
            branch: 分支名

        Returns:
            本地仓库路径
        """
        repo_path = self.repos_base_path / f"repo_{repo_id}"

        if local_path and os.path.isdir(local_path):
            logger.info(f"使用现有本地路径: {local_path}")
            return Path(local_path)

        if repo_path.exists():
            # 已存在，执行 pull
            logger.info(f"更新仓库: {repo_path}")
            try:
                result = await asyncio.wait_for(
                    self._run_git("pull", cwd=str(repo_path)),
                    timeout=settings.GIT_CLONE_TIMEOUT,
                )
                if result.returncode != 0:
                    raise RuntimeError(f"git pull 失败: {result.stderr.strip()}")
            except Exception as e:
                logger.warning(f"git pull 失败，删除后重新克隆: {e}")
                shutil.rmtree(repo_path, ignore_errors=True)
            else:
                return repo_path

        # 克隆新仓库
        if git_url:
            logger.info(f"克隆仓库: {git_url} -> {repo_path}")
            try:
                result = await asyncio.wait_for(
                    self._run_git(
                        "clone", "--branch", branch, "--depth", "1",
                        git_url, str(repo_path),
                    ),
                    timeout=settings.GIT_CLONE_TIMEOUT,
                )
                if result.returncode != 0:
                    err = result.stderr.strip() or result.stdout.strip() or f"exit={result.returncode}"
                    raise RuntimeError(f"git clone 失败 (exit={result.returncode}): {err}")
            except subprocess.TimeoutExpired:
                msg = f"git clone 超时（>{settings.GIT_CLONE_TIMEOUT}s），请检查网络或调大 GIT_CLONE_TIMEOUT"
                logger.error(msg)
                raise RuntimeError(msg)
            except Exception as e:
                msg = f"git clone 异常 [{type(e).__name__}]: {e}"
                logger.error(msg)
                raise RuntimeError(msg)
            return repo_path
        else:
            raise ValueError("需要提供 git_url 或 local_path")

    def scan_files(self, repo_path: Path) -> List[Path]:
        """扫描仓库中的代码和文档文件"""
        files = []

        # 跳过的目录
        skip_dirs = {
            ".git", "node_modules", "__pycache__", ".idea", ".vscode",
            "dist", "build", "target", ".next", ".venv", "venv",
        }

        for root, dirs, filenames in os.walk(repo_path):
            # 跳过不需要的目录
            dirs[:] = [d for d in dirs if d not in skip_dirs]

            for filename in filenames:
                filepath = Path(root) / filename
                suffix = filepath.suffix.lower()
                if suffix in CODE_EXTENSIONS or suffix in DOC_EXTENSIONS or suffix == ".txt":
                    files.append(filepath)

        logger.info(f"扫描到 {len(files)} 个文件")
        return files

    async def process_repository(
        self,
        repo_id: int,
        repo_path: Path,
        db_session,
    ) -> Dict:
        """
        处理整个仓库：扫描文件 -> 解析代码 -> 生成向量 -> 存入数据库

        Args:
            repo_id: 仓库 ID
            repo_path: 本地仓库路径
            db_session: SQLAlchemy 异步会话

        Returns:
            处理统计信息
        """
        from app.models.document import Document, CodeChunk
        from sqlalchemy import select

        files = self.scan_files(repo_path)
        stats = {"files": 0, "chunks": 0, "vectors": 0, "errors": 0}

        for filepath in files:
            try:
                # 读取文件内容
                rel_path = str(filepath.relative_to(repo_path))
                content = filepath.read_text(encoding="utf-8", errors="ignore")
                if not content.strip():
                    continue

                # 解析代码分块
                chunks = parse_file(rel_path, content)
                if not chunks:
                    continue

                # 创建 Document 记录
                doc = Document(
                    repo_id=repo_id,
                    file_path=rel_path,
                    file_name=filepath.name,
                    file_type=filepath.suffix.lower().lstrip("."),
                    content=content[:50000],  # 限制存储大小
                    size_bytes=len(content.encode("utf-8")),
                    line_count=content.count("\n") + 1,
                )
                db_session.add(doc)
                await db_session.flush()  # 获取 doc.id

                # 批量生成向量（每 32 个一批）
                batch_size = 32
                for batch_start in range(0, len(chunks), batch_size):
                    batch_chunks = chunks[batch_start:batch_start + batch_size]
                    batch_texts = [c.content for c in batch_chunks]

                    # 生成向量
                    vectors = embedding_manager.get_embeddings(batch_texts)

                    # 存入 FAISS
                    metadatas = []
                    for i, chunk in enumerate(batch_chunks):
                        metadatas.append({
                            "repo_id": repo_id,
                            "document_id": doc.id,
                            "file_path": rel_path,
                            "file_name": filepath.name,
                            "chunk_index": batch_start + i,
                            "chunk_type": chunk.chunk_type,
                            "chunk_name": chunk.chunk_name,
                            "start_line": chunk.start_line,
                            "end_line": chunk.end_line,
                            "content": chunk.content,
                        })

                    vector_ids = faiss_store.add_vectors(vectors, metadatas)

                    # 创建 CodeChunk 记录
                    for i, chunk in enumerate(batch_chunks):
                        db_session.add(CodeChunk(
                            document_id=doc.id,
                            repo_id=repo_id,
                            chunk_index=batch_start + i,
                            chunk_type=chunk.chunk_type,
                            chunk_name=chunk.chunk_name,
                            content=chunk.content,
                            start_line=chunk.start_line,
                            end_line=chunk.end_line,
                            token_count=len(chunk.content.split()),
                            vector_id=vector_ids[i] if i < len(vector_ids) else None,
                        ))

                stats["files"] += 1
                stats["chunks"] += len(chunks)
                stats["vectors"] += len(chunks)

            except Exception as e:
                stats["errors"] += 1
                logger.error(f"处理文件失败 {filepath}: {e}")
                continue

        # 更新仓库统计
        from app.models.repository import Repository
        result = await db_session.execute(select(Repository).where(Repository.id == repo_id))
        repo = result.scalar_one_or_none()
        if repo:
            repo.status = "ready"
            repo.total_files = stats["files"]
            repo.total_chunks = stats["chunks"]
            repo.last_synced_at = datetime.utcnow()

        await db_session.commit()
        logger.info(f"仓库 {repo_id} 处理完成: {stats}")
        return stats


# 全局实例
git_service = GitService()
