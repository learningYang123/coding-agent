# coding-agent

企业代码智能助手，使用 RAG 检索代码与文档，并提供错误日志分析和 Python 代码沙箱。前端采用 React，后端采用 FastAPI。

## 功能

- **代码检索与问答**：FAISS 向量检索、tree-sitter 代码分块、文件级检索兜底和项目概览。
- **Agent 诊断**：解析错误日志，检索相关代码，生成诊断与修复建议。
- **多模型接入**：DeepSeek、Ollama、智谱、千问、OpenAI、Gemini、硅基流动、OpenRouter，以及其他 OpenAI Chat Completions 兼容服务。
- **模型管理**：添加、编辑、删除模型，获取模型列表、测试连接、设置默认模型；在聊天输入框上方切换模型。
- **账号与权限**：登录、自助注册、管理员用户管理、仓库访问权限控制。
- **流式对话**：通过 SSE 输出回答、思考过程、工具步骤和引用来源。
- **代码沙箱**：执行 Python 片段，提供代码检查、超时和输出大小限制。
- **界面**：保留科技感渐变和玻璃卡片，使用更亮的蓝灰配色；聊天页及模型页均提供账号菜单。

## 技术栈

| 组件 | 实现 |
| --- | --- |
| 后端 | Python 3.12、FastAPI、Uvicorn |
| 数据库 | SQLAlchemy 2.x、SQLite / aiosqlite |
| 认证 | JWT、bcrypt |
| 语义检索 | Sentence Transformers、FAISS、tree-sitter |
| 模型调用 | HTTPX、OpenAI Chat Completions 兼容协议 |
| Agent | Python 诊断流程与工具模块 |
| 前端 | React 18、Vite 5、TypeScript、Ant Design、Tailwind CSS、Zustand |
| 模型密钥保存 | cryptography / Fernet |

## 快速启动

需要 Python 3.12、Node.js 20 或更新版本，以及 Git。以下命令以 Windows PowerShell 为例。

### 1. 获取代码

```powershell
git clone https://github.com/learningYang123/coding-agent.git
cd coding-agent
```

已有项目时，直接进入项目根目录。后端必须从根目录启动，保证 `.env`、数据库、向量库与模型目录使用同一组相对路径。

### 2. 安装后端依赖

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install torch --index-url https://download.pytorch.org/whl/cpu
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

也可以使用已安装的 uv：

```powershell
uv venv --python 3.12
uv pip install --python .venv\Scripts\python.exe torch --index-url https://download.pytorch.org/whl/cpu
uv pip install --python .venv\Scripts\python.exe -r backend\requirements.txt
```

`tree-sitter-languages==1.10.2` 需要 `tree-sitter>=0.21.3,<0.22`，依赖文件已限定兼容范围。

### 3. 配置环境变量

```powershell
Copy-Item backend\.env.example .env
```

`.env` 放在项目根目录。可以直接在登录后的模型设置中配置个人模型；项目级模型参数使用 `LLM_PROVIDER`、`LLM_BASE_URL`、`LLM_API_KEY`、`LLM_MODEL`，不使用 `DEEPSEEK_API_KEY`。

本地 Embedding 默认使用 `all-MiniLM-L6-v2`。首次运行会尝试下载到 `data/embeddings/all-MiniLM-L6-v2`；下载失败时会退回开发用的随机向量，无法提供可靠的语义检索。离线环境请预先放好模型文件。

### 4. 启动后端

在项目根目录运行：

```powershell
.\.venv\Scripts\python.exe backend\run.py
```

- 后端：<http://localhost:8000>
- API 文档：<http://localhost:8000/docs>
- 健康检查：<http://localhost:8000/api/v1/health>

### 5. 启动前端

另开一个终端：

```powershell
cd frontend
npm.cmd ci
npm.cmd run dev
```

访问 <http://localhost:5173>。前端通过 Vite 将 `/api` 请求转发到 `127.0.0.1:8000`。

依赖安装好后，也可直接运行 `backend/start.bat` 和 `frontend/start.bat`。Linux/macOS 使用 `.venv/bin/python` 和 `npm` 替换上面的 Windows 命令。

## 登录与账号

登录功能和注册功能均保留。未登录时访问工作台会进入登录页；已有登录状态时，也可以直接访问 `/login`。聊天页和模型页右上角的账号菜单提供“打开登录页”和“退出登录”。

登录页不会预填或展示管理员账号与密码。开发环境首次初始化仍会创建管理员，默认用户名为 `admin`、密码为 `admin123`；可以在首次初始化数据库前通过 `ADMIN_USERNAME` 和 `ADMIN_PASSWORD` 修改。

普通用户可以从登录页注册。管理员可以管理用户、仓库及仓库权限。部署到共享环境前，请配置独立的 `SECRET_KEY` 和管理员密码。

## 模型设置

登录后点击聊天页顶部的 **模型设置**：

1. 选择供应商或平台。
2. 填写显示名称、API 基础地址、模型 ID，以及平台需要的 API Key。
3. 可点击 **获取列表** 或 **测试连接**。
4. 保存后，在聊天输入框上方选择模型。首个模型自动成为默认模型。

| 平台 | API 基础地址 | 说明 |
| --- | --- | --- |
| DeepSeek | `https://api.deepseek.com` | 使用 DeepSeek 开放平台密钥 |
| Ollama | `http://localhost:11434/v1` | 本地服务通常无需密钥 |
| 智谱 GLM | `https://open.bigmodel.cn/api/paas/v4` | Coding Plan 使用对应专用地址 |
| 千问 / 阿里云百炼 | `https://dashscope.aliyuncs.com/compatible-mode/v1` | 按密钥地域或业务空间修改地址 |
| OpenAI | `https://api.openai.com/v1` | 支持兼容的对话和推理模型 |
| Gemini | `https://generativelanguage.googleapis.com/v1beta/openai` | 使用 Gemini API 密钥 |
| 硅基流动 | `https://api.siliconflow.cn/v1` | 使用平台提供的完整模型 ID |
| OpenRouter | `https://openrouter.ai/api/v1` | 使用包含供应商前缀的完整模型 ID |
| 自定义 / One API / New API | 自行填写 | 服务必须支持 OpenAI Chat Completions 协议 |

基础地址和模型 ID 都可以手动修改。模型页提供供应商官方文档链接；预置 ID 仅供填写参考，以账户实际可用模型为准。获取列表失败的平台仍可手动输入模型 ID。

### Ollama 本地模型

先启动 Ollama 并下载需要的模型。例如：

```powershell
ollama pull qwen3:8b
```

在模型设置中选择 Ollama，点击 **获取列表** 读取已安装模型。地址中的 `localhost` 指后端所在电脑；如果 Ollama 在另一台电脑上运行，请改成对应地址。连接测试会发送简短请求，本地模型冷启动可能需要等待。

### 密钥与默认模型

- 模型配置按登录用户隔离，不在 API 响应中回显密钥。
- 密钥在后端加密保存。编辑时留空保留已有密钥；更换供应商时需重新填写密钥。
- 默认模型用于未指定 `model_id` 的请求。没有个人模型配置时，继续使用项目 `.env` 中的 LLM 配置。
- RAG 问答、Agent 问答和错误日志分析均支持模型配置。
- 保存配置不要求先测试成功；测试连接会发送一次实际模型请求。

## 本地数据与备份

运行数据由程序在项目根目录的 `data/` 中创建，不上传到 GitHub：

| 路径 | 用途 |
| --- | --- |
| `data/app.db` | 用户、仓库、会话和模型配置 |
| `data/faiss/` | 向量索引与元数据 |
| `data/repos/` | 拉取的仓库 |
| `data/embeddings/` | 本地 Embedding 模型 |
| `data/logs/` | 应用日志 |
| `data/.model-key` | 模型密钥加密所用的独立密钥 |

备份时请同时保留数据库和 `data/.model-key`，并单独保存 `.env`。也可以通过 `MODEL_ENCRYPTION_KEY` 指定 Fernet 密钥，或使用 `MODEL_ENCRYPTION_KEY_FILE` 修改密钥文件位置。丢失加密密钥后，需要重新输入已保存的模型密钥。

源码仓库只包含程序、依赖清单、示例配置和示例代码，不包含本地数据库、检索内容、模型权重、个人密钥、日志、npm 缓存或虚拟环境。

## API

认证后的请求使用 `Authorization: Bearer <token>`。完整请求结构见运行中的 `/docs`。

| 模块 | 主要接口 |
| --- | --- |
| 认证 | `POST /api/v1/auth/login`、`POST /api/v1/auth/register`、`GET /api/v1/auth/me` |
| 用户管理 | `/api/v1/auth/admin/users` 及用户编辑、密码重置、删除接口 |
| 仓库 | `/api/v1/repositories` 及同步、权限管理接口 |
| 对话 | `POST /api/v1/chat/ask`、`POST /api/v1/chat/stream` |
| 错误分析 | `POST /api/v1/chat/analyze-error`、`POST /api/v1/chat/analyze-error/stream` |
| 沙箱 | `POST /api/v1/chat/run-code`、`GET /api/v1/chat/sandbox/status` |
| 会话 | `/api/v1/chat/conversations` 及消息读取、删除接口 |
| 供应商预设 | `GET /api/v1/models/providers` |
| 模型配置 | `GET /api/v1/models`、`POST /api/v1/models`、`PUT /api/v1/models/{id}`、`DELETE /api/v1/models/{id}` |
| 默认模型 | `POST /api/v1/models/{id}/default` |
| 连接测试 | `POST /api/v1/models/test-connection`、`POST /api/v1/models/{id}/test` |
| 模型列表 | `POST /api/v1/models/discover` |

聊天请求可以包含 `query`、`mode`（`rag` / `agent`）、`repo_ids`、`model_id`、`conversation_id` 和 `error_log`。

SSE 事件类型为 `sources`、`token`、`thinking`、`agent_step`、`done`、`error`。例如：

```text
event: token
data: "你好"

event: done
data: {"answer":"你好","sources":[],"conversation_id":1}
```

## 验证

在项目根目录运行后端测试：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s backend/tests -v
```

前端构建：

```powershell
cd frontend
npm.cmd run build
```

目前包含 9 项自动化测试，覆盖供应商协议与流式解析、推理模型参数、地址校验、密钥加密与保留、认证和用户隔离、默认模型、模型发现及 RAG/Agent 模型选择。供应商协议使用模拟 HTTP 响应验证；本地 Ollama `qwen3:8b` 已验证实际连接。云端实际调用需要有效的平台密钥。

已验证的开发环境：Python 3.12.7、Node.js 24.18.0。

## 项目结构

```text
coding-agent/
├── backend/
│   ├── app/
│   │   ├── api/routes/        # 认证、仓库、对话与模型设置接口
│   │   ├── core/              # 配置、认证、日志与密钥加密
│   │   ├── db/                # 数据库连接
│   │   ├── models/            # 用户、仓库、会话与模型配置表
│   │   ├── rag/               # 分块、向量化、检索与生成
│   │   ├── agent/             # 错误分析与沙箱工具
│   │   ├── schemas/           # 请求和响应模型
│   │   └── main.py            # FastAPI 入口
│   ├── data/sample_code/      # 示例代码
│   ├── tests/                 # 模型设置和路由测试
│   ├── requirements.txt
│   ├── run.py
│   └── start.bat
├── frontend/
│   ├── src/
│   │   ├── api/               # HTTP 与 SSE 客户端
│   │   ├── components/        # 账号菜单等共享组件
│   │   ├── pages/             # 登录、注册、聊天、仓库、用户与模型页面
│   │   └── store/             # 状态管理
│   ├── package.json
│   └── start.bat
├── README.md
└── .gitignore
```

## 许可证

MIT
