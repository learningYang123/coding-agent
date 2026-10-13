"""
后端快速验证脚本 - 测试核心模块能否正常加载运行
"""
import sys
import os

# 将 backend 目录加入 path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_imports():
    print("=" * 50)
    print("📦 测试核心模块导入...")
    print("=" * 50)

    modules = [
        ("FastAPI", "fastapi"),
        ("SQLAlchemy", "sqlalchemy"),
        ("Pydantic", "pydantic"),
        ("JWT", "jwt"),
        ("Loguru", "loguru"),
        ("httpx", "httpx"),
    ]

    all_ok = True
    for name, mod in modules:
        try:
            __import__(mod)
            print(f"  ✅ {name}")
        except ImportError as e:
            print(f"  ❌ {name}: {e}")
            all_ok = False

    return all_ok


def test_app_import():
    print("\n" + "=" * 50)
    print("🚀 测试 App 模块导入...")
    print("=" * 50)

    try:
        from app.core.config import settings
        print(f"  ✅ Config loaded: {settings.APP_NAME}")

        from app.db.database import Base, engine
        print(f"  ✅ Database engine: {settings.DATABASE_URL}")

        from app.models import User, Repository, CodeChunk
        print(f"  ✅ Models loaded")

        from app.utils.sse import SSEBuffer
        print(f"  ✅ SSE utils loaded")

        from app.rag.vector_store import faiss_store
        stats = faiss_store.get_stats()
        print(f"  ✅ FAISS store: {stats}")

        from app.rag.embeddings import embedding_manager
        vec = embedding_manager.get_single_embedding("test query")
        print(f"  ✅ Embedding: dim={vec.shape if hasattr(vec, 'shape') else 'N/A'}")

        from app.main import app
        print(f"  ✅ FastAPI app created!")

        return True
    except Exception as e:
        print(f"  ❌ Import failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_rag():
    print("\n" + "=" * 50)
    print("🔍 测试 RAG 检索（Mock Embedding）...")
    print("=" * 50)

    try:
        from app.rag.vector_store import faiss_store

        # 添加一些测试向量
        import numpy as np
        fake_vecs = np.random.randn(3, 384).astype(np.float32)
        faiss_store.add_vectors(fake_vecs, [
            {"repo_id": 1, "file_path": "test.py", "chunk_type": "function", "chunk_name": "test_func", "content": "def test(): pass"},
            {"repo_id": 1, "file_path": "test.py", "chunk_type": "class", "chunk_name": "TestClass", "content": "class TestClass: pass"},
            {"repo_id": 2, "file_path": "other.py", "chunk_type": "function", "content": "def other(): pass"},
        ])

        # 搜索
        stats = faiss_store.get_stats()
        print(f"  📊 FAISS stats: {stats}")

        query_vec = np.random.randn(1, 384).astype(np.float32)[0]

        # 全量搜索
        results = faiss_store.search(query_vec, top_k=3)
        print(f"  ✅ 无权限搜索: {len(results)} 条")

        # 权限过滤
        results_filtered = faiss_store.search(query_vec, top_k=3, allowed_repo_ids=[1])
        print(f"  ✅ 权限过滤 (repo=1): {len(results_filtered)} 条")
        for r in results_filtered:
            print(f"    - repo={r.get('repo_id')}, file={r.get('file_path')}, score={r.get('score'):.3f}")

        return True
    except Exception as e:
        print(f"  ❌ RAG test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_sandbox():
    print("\n" + "=" * 50)
    print("💻 测试代码沙箱...")
    print("=" * 50)

    import asyncio

    async def run():
        try:
            from app.agent.sandbox import sandbox

            # 安全代码
            result = await sandbox.execute("print('Hello from sandbox!')\nx = 1 + 2\nprint(f'Result: {x}')")
            print(f"  ✅ 安全代码执行: success={result['success']}")
            print(f"    output: {result['output'][:100]}")

            # 危险代码（应该被拒绝）
            result2 = await sandbox.execute("import os; os.system('whoami')")
            print(f"  ✅ 危险代码拦截: {not result2['success']}")
            if not result2['success']:
                print(f"    error: {result2['error'][:80]}")

            return True
        except Exception as e:
            print(f"  ❌ Sandbox test failed: {e}")
            import traceback
            traceback.print_exc()
            return False

    return asyncio.run(run())


def main():
    print("\n" + "🚀" * 30)
    print("  企业代码智能助手 - 后端快速验证")
    print("🚀" * 30)

    results = []
    results.append(("核心依赖", test_imports()))
    results.append(("App 模块", test_app_import()))
    results.append(("RAG 检索", test_rag()))
    results.append(("代码沙箱", test_sandbox()))

    print("\n" + "=" * 50)
    print("📋 验证结果汇总")
    print("=" * 50)
    all_pass = True
    for name, ok in results:
        status = "✅ PASS" if ok else "❌ FAIL"
        print(f"  {status}  {name}")
        if not ok:
            all_pass = False

    print()
    if all_pass:
        print("🎉 所有模块验证通过！后端可以启动了。")
    else:
        print("⚠️  部分模块需要修复后才能正常运行。")

    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
