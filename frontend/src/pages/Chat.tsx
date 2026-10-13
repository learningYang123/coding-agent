import { useEffect, useRef, useState, useCallback } from 'react'
import { Layout, Input, Button, Select, Switch, Dropdown, Space, Badge, Empty, message } from 'antd'
import {
  SendOutlined,
  CodeOutlined,
  RobotOutlined,
  PlusOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  LogoutOutlined,
  SettingOutlined,
  HistoryOutlined,
  UploadOutlined,
  FileTextOutlined,
  ClearOutlined,
  ClusterOutlined,
  TeamOutlined,
} from '@ant-design/icons'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import hljs from 'highlight.js'

import { useNavigate } from 'react-router-dom'
import { useAuthStore, useChatStore, useRepoStore, useModelStore } from '@/store'
import { chatApi, repoApi, SSEEvent } from '@/api/client'
import AccountMenu from '@/components/AccountMenu'

const { Header, Sider, Content } = Layout
const { TextArea } = Input

// ============ 代码高亮组件 ============
function CodeBlock({ language, value }: { language?: string; value: string }) {
  const ref = useRef<HTMLPreElement>(null)

  useEffect(() => {
    if (ref.current) {
      try {
        if (language && hljs.getLanguage(language)) {
          hljs.highlightElement(ref.current)
        } else {
          ref.current.innerHTML = hljs.highlightAuto(value).value
        }
      } catch {
        ref.current.textContent = value
      }
    }
  }, [value, language])

  return (
    <pre ref={ref} className="!bg-[#172438] !rounded-lg !p-4 !text-sm !overflow-x-auto">
      <code className={`language-${language || 'plaintext'}`}>{value}</code>
    </pre>
  )
}

// ============ 消息渲染 ============
function MessageBubble({ message }: { message: any }) {
  const isUser = message.role === 'user'

  if (isUser) {
    return (
      <div className="flex justify-end mb-4">
        <div className="max-w-[75%] px-5 py-3 rounded-2xl rounded-br-md bg-gradient-to-r from-primary-500 to-blue-600 text-white shadow-lg shadow-primary-500/20">
          <p className="whitespace-pre-wrap break-words">{message.content}</p>
        </div>
      </div>
    )
  }

  return (
    <div className="flex justify-start mb-4 gap-3">
      <div className="flex-shrink-0 w-9 h-9 rounded-xl bg-gradient-to-br from-primary-500 to-purple-600 flex items-center justify-center shadow-lg">
        <RobotOutlined className="text-white text-lg" />
      </div>

      <div className="max-w-[75%] flex-1">
        {/* Agent 步骤 */}
        {message.agentSteps?.length > 0 && (
          <div className="mb-3 space-y-1">
            {message.agentSteps.map((step: any, i: number) => (
              <div key={i} className="agent-step flex items-center gap-2 text-xs text-surface-muted bg-surface-card/50 rounded-lg px-3 py-1.5">
                <span className="w-2 h-2 rounded-full bg-primary-500 animate-pulse" />
                <span>{step.step}</span>
                {step.detail && <span className="opacity-60">- {typeof step.detail === 'string' ? step.detail : JSON.stringify(step.detail)}</span>}
              </div>
            ))}
          </div>
        )}

        {/* 思考过程 */}
        {message.thinking && (
          <div className="mb-3 p-3 rounded-lg bg-yellow-500/5 border border-yellow-500/20 text-xs text-yellow-300/80 whitespace-pre-wrap">
            💭 {message.thinking}
          </div>
        )}

        {/* AI 回答 */}
        <div
          className={`px-5 py-3 rounded-2xl rounded-bl-md bg-surface-card/80 border border-surface-border chat-markdown max-w-none ${
            message.streaming ? 'typing-cursor' : ''
          }`}
        >
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{
              code({ inline, className, children, ...props }: any) {
                const match = /language-(\w+)/.exec(className || '')
                return !inline && match ? (
                  <CodeBlock language={match[1]} value={String(children).replace(/\n$/, '')} />
                ) : (
                  <code className={className} {...props}>
                    {children}
                  </code>
                )
              },
              pre({ children }: any) {
                return children
              },
            }}
          >
            {message.content || (message.streaming ? '' : '（无内容）')}
          </ReactMarkdown>
        </div>

        {/* 引用来源 */}
        {message.sources?.length > 0 && (
          <div className="mt-3 space-y-2">
            <p className="text-xs text-surface-muted">📎 引用来源 ({message.sources.length})</p>
            {message.sources.slice(0, 5).map((src: any, i: number) => (
              <details key={i} className="group">
                <summary className="cursor-pointer text-xs text-primary-400 hover:text-primary-300 transition-colors flex items-center gap-2 px-3 py-2 rounded-lg bg-surface-card/50 border border-surface-border hover:border-primary-500/50">
                  <FileTextOutlined />
                  <span className="truncate">{src.file_path}</span>
                  {src.chunk_name && <span className="opacity-60">- {src.chunk_name}</span>}
                  {src.score !== undefined && <span className="ml-auto opacity-60">相关度: {(src.score * 100).toFixed(1)}%</span>}
                </summary>
                <pre className="mt-1 p-3 text-xs bg-[#172438] rounded-lg overflow-x-auto max-h-60">
                  <code className="text-slate-200">{src.content?.slice(0, 2000)}</code>
                </pre>
              </details>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

// ============ 仓库选择器 ============
function RepoSelector() {
  const { repos, selectedRepoIds, toggleRepo, setSelectedRepos } = useRepoStore()
  const [open, setOpen] = useState(false)

  return (
    <Dropdown
      open={open}
      onOpenChange={setOpen}
      menu={{
        items: [
          {
            key: 'all',
            label: (
              <span
                onClick={() => {
                  setSelectedRepos(repos.map((r) => r.id))
                  setOpen(false)
                }}
              >
                全部仓库
              </span>
            ),
          },
          ...repos.map((repo) => ({
            key: String(repo.id),
            label: (
              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={selectedRepoIds.includes(repo.id)}
                  onChange={(e) => {
                    e.stopPropagation()
                    toggleRepo(repo.id)
                  }}
                />
                <span className={repo.status === 'ready' ? '' : 'opacity-50'}>{repo.name}</span>
                <Badge
                  status={repo.status === 'ready' ? 'success' : repo.status === 'indexing' ? 'processing' : 'default'}
                  className="!ml-auto"
                />
              </div>
            ),
          })),
        ],
      }}
    >
      <Button icon={<CodeOutlined />} className="!bg-surface-card !border-surface-border">
        {selectedRepoIds.length > 0 ? `${selectedRepoIds.length} 个仓库` : '选择仓库'}
      </Button>
    </Dropdown>
  )
}

// ============ 主聊天页面 ============
export default function ChatPage() {
  const navigate = useNavigate()
  const [collapsed, setCollapsed] = useState(true)
  const [input, setInput] = useState('')
  const [errorLog, setErrorLog] = useState('')
  const [showErrorLog, setShowErrorLog] = useState(false)
  const [errorInputMode, setErrorInputMode] = useState<'inline' | 'upload'>('inline')
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const cancelFnRef = useRef<(() => void) | null>(null)

  const logout = useAuthStore((s) => s.logout)
  const user = useAuthStore((s) => s.user)
  const isAdmin = useAuthStore((s) => s.isAdmin())
  const { models, selectedModelId, select: selectModel, refresh: refreshModels, loading: modelsLoading } = useModelStore()
  const defaultModel = models.find((model) => model.is_default)

  const {
    mode,
    messages,
    conversations,
    isStreaming,
    setMode,
    appendMessage,
    updateLastAssistant,
    startStreaming,
    stopStreaming,
    clearMessages,
    setConversations,
    setCurrentConversation,
  } = useChatStore()

  const { repos, selectedRepoIds, setRepos, setSelectedRepos } = useRepoStore()

  // 加载仓库列表
  useEffect(() => {
    refreshModels().catch(() => message.error('模型配置加载失败，请到模型设置中重试'))
    repoApi
      .list()
      .then((data) => {
        setRepos(data)
        setSelectedRepos(data.filter((r: any) => r.status === 'ready').map((r: any) => r.id))
      })
      .catch(() => {})
  }, [])

  // 自动滚动到底部
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleSend = useCallback(() => {
    if (!input.trim() || isStreaming) return

    const query = input.trim()
    setInput('')
    startStreaming()

    // 添加用户消息
    appendMessage({
      id: `user-${Date.now()}`,
      role: 'user',
      content: query,
    })

    // 添加空的 assistant 消息占位
    appendMessage({
      id: `assistant-${Date.now()}`,
      role: 'assistant',
      content: '',
      streaming: true,
      agentSteps: [],
    })

    // 收集事件
    let fullContent = ''
    let sources: any[] = []
    let thinking = ''
    const agentSteps: any[] = []

    const onEvent = (event: SSEEvent) => {
      switch (event.type) {
        case 'sources':
          sources = Array.isArray(event.data) ? event.data : []
          break

        case 'token':
          fullContent += event.data
          updateLastAssistant({ content: fullContent })
          break

        case 'thinking':
          thinking += (thinking ? '\n' : '') + event.data
          updateLastAssistant({ thinking })
          break

        case 'agent_step':
          agentSteps.push(event.data)
          updateLastAssistant({ agentSteps: [...agentSteps] })
          break

        case 'done':
          stopStreaming()
          const final = event.data || {}
          updateLastAssistant({
            content: final.answer || fullContent,
            sources: final.sources || sources,
            streaming: false,
          })
          if (final.conversation_id) {
            setCurrentConversation(final.conversation_id)
          }
          break

        case 'error':
          stopStreaming()
          updateLastAssistant({
            content: '❌ ' + (event.data?.message || '未知错误'),
            streaming: false,
          })
          break
      }
    }

    cancelFnRef.current = chatApi.stream(
      query,
      mode,
      selectedRepoIds,
      undefined,
      onEvent,
      selectedModelId ?? undefined,
      mode === 'agent' ? errorLog.trim() || undefined : undefined,
    )
  }, [input, isStreaming, mode, selectedRepoIds, selectedModelId, errorLog])

  const handleStop = () => {
    cancelFnRef.current?.()
    stopStreaming()
    updateLastAssistant({ streaming: false })
  }

  const handleClear = () => {
    clearMessages()
  }

  const handleLogout = () => {
    logout()
    navigate('/login', { replace: true })
  }

  return (
    <Layout className="h-screen tech-bg">
      {/* 侧边栏 */}
      <Sider
        trigger={null}
        collapsible
        collapsed={collapsed}
        width={280}
        className="!bg-surface-card !border-r !border-surface-border"
      >
        <div className="h-full flex flex-col">
          {/* Logo */}
          <div className="h-14 flex items-center justify-center border-b border-surface-border">
            <CodeOutlined className="text-primary-500 text-xl" />
            {!collapsed && <span className="ml-2 font-bold">代码助手</span>}
          </div>

          {/* 模式切换 */}
          {!collapsed && (
            <div className="p-4">
              <p className="text-xs text-surface-muted mb-2">模式</p>
              <div className="flex gap-2">
                <button
                  onClick={() => setMode('rag')}
                  className={`flex-1 py-2 px-3 rounded-lg text-xs transition-all flex items-center justify-center gap-1 ${
                    mode === 'rag'
                      ? 'bg-primary-500 text-white shadow-lg shadow-primary-500/30'
                      : 'bg-surface-bg text-surface-muted hover:text-primary-500'
                  }`}
                >
                  <CodeOutlined /> RAG
                </button>
                <button
                  onClick={() => setMode('agent')}
                  className={`flex-1 py-2 px-3 rounded-lg text-xs transition-all flex items-center justify-center gap-1 ${
                    mode === 'agent'
                      ? 'bg-gradient-to-r from-primary-500 to-purple-500 text-white shadow-lg shadow-primary-500/30'
                      : 'bg-surface-bg text-surface-muted hover:text-primary-500'
                  }`}
                >
                  <RobotOutlined /> Agent
                </button>
              </div>
            </div>
          )}

          {/* 历史对话 */}
          {!collapsed && (
            <div className="flex-1 overflow-y-auto px-2">
              <div className="flex items-center justify-between p-2 text-xs text-surface-muted">
                <span>历史对话</span>
                <PlusOutlined className="cursor-pointer hover:text-primary-500" onClick={handleClear} />
              </div>
              <div className="space-y-1">
                {messages.length === 0 && (
                  <p className="text-center text-surface-muted text-xs py-4">开始一段新对话</p>
                )}
              </div>
            </div>
          )}

          {/* 用户信息 */}
          <div className="border-t border-surface-border p-3">
            {!collapsed ? (
              <div className="flex items-center gap-3">
                <div className="w-8 h-8 rounded-full bg-gradient-to-br from-primary-500 to-purple-500 flex items-center justify-center text-white text-sm font-bold">
                  {user?.username?.[0]?.toUpperCase() || 'U'}
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm truncate">{user?.username}</p>
                  <p className="text-xs text-surface-muted">{user?.role === 'admin' ? '管理员' : '开发者'}</p>
                </div>
                <Button
                  type="text"
                  size="small"
                  icon={<LogoutOutlined />}
                  onClick={handleLogout}
                  aria-label="退出登录"
                  className="!text-surface-muted hover:!text-red-400"
                />
              </div>
            ) : (
              <div className="text-center">
                <Button
                  type="text"
                  size="small"
                  icon={<LogoutOutlined />}
                  onClick={handleLogout}
                  aria-label="退出登录"
                  className="!text-surface-muted"
                />
              </div>
            )}
          </div>
        </div>
      </Sider>

      {/* 主内容区 */}
      <Layout className="!bg-transparent">
        {/* 顶部栏 */}
        <Header className="chat-header !bg-surface-card/90 backdrop-blur border-b border-surface-border flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Button
              type="text"
              icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
              onClick={() => setCollapsed(!collapsed)}
              className="!text-surface-text"
            />
            <h2 className="text-base font-medium">
              {mode === 'agent' ? '🤖 Agent 智能助手' : '💡 RAG 代码问答'}
            </h2>
          </div>

          <div className="chat-header-actions flex items-center">
            <Button icon={<SettingOutlined />} onClick={() => navigate('/models')} disabled={isStreaming}>模型设置</Button>
            {isAdmin && (
              <Button
                icon={<TeamOutlined />}
                onClick={() => navigate('/users')}
                className="!bg-surface-card !border-surface-border"
              >
                用户管理
              </Button>
            )}
            <Button
              icon={<ClusterOutlined />}
              onClick={() => navigate('/repos')}
              className="!bg-surface-card !border-surface-border"
            >
              仓库管理
            </Button>
            <RepoSelector />
            <Button
              icon={<ClearOutlined />}
              onClick={handleClear}
              disabled={messages.length === 0 || isStreaming}
              className="!bg-surface-card !border-surface-border"
            >
              清空
            </Button>
            <AccountMenu />
          </div>
        </Header>

        {/* 消息区 */}
        <Content className="flex flex-col overflow-hidden">
          {/* 空状态 */}
          {messages.length === 0 && (
            <div className="flex-1 flex items-center justify-center">
              <div className="text-center">
                <div className="inline-flex items-center justify-center w-20 h-20 rounded-2xl bg-gradient-to-br from-primary-500/20 to-purple-500/20 mb-6">
                  {mode === 'agent' ? (
                    <RobotOutlined className="text-4xl text-primary-400" />
                  ) : (
                    <CodeOutlined className="text-4xl text-primary-400" />
                  )}
                </div>
                <h2 className="text-2xl font-bold mb-2">
                  {mode === 'agent' ? 'Agent 模式' : 'RAG 模式'}
                </h2>
                <p className="text-surface-muted mb-8 max-w-md">
                  {mode === 'agent'
                    ? '智能 Agent 可以分析错误日志、搜索代码库、在沙箱中执行代码，帮你定位和解决问题'
                    : '基于 RAG 检索技术，从企业代码库中找到相关代码片段，回答业务逻辑问题'}
                </p>
                <div className="flex flex-wrap gap-2 justify-center max-w-xl mx-auto">
                  {[
                    '订单状态流转逻辑是怎样的？',
                    '帮我找一下支付相关的代码',
                    '库存预占失败可能是什么原因？',
                    '如何实现订单取消流程？',
                  ].map((q) => (
                    <button
                      key={q}
                      onClick={() => {
                        setInput(q)
                      }}
                      className="px-4 py-2 text-sm rounded-full bg-surface-card border border-surface-border hover:border-primary-500 hover:text-primary-400 transition-all"
                    >
                      {q}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* 消息列表 */}
          {messages.length > 0 && (
            <div className="flex-1 overflow-y-auto px-6 py-6 max-w-4xl mx-auto w-full">
              {messages.map((msg) => (
                <MessageBubble key={msg.id} message={msg} />
              ))}
              <div ref={messagesEndRef} />
            </div>
          )}

          {/* 输入区 */}
          <div className="border-t border-surface-border bg-surface-card/60 backdrop-blur p-4">
            <div className="max-w-4xl mx-auto">
              <div className="flex items-center gap-3 mb-3">
                <span className="text-xs text-surface-muted">对话模型</span>
                <Select
                  aria-label="选择聊天模型"
                  className="model-picker"
                  size="small"
                  value={selectedModelId ?? 'default'}
                  loading={modelsLoading}
                  disabled={isStreaming}
                  onChange={(value) => selectModel(value === 'default' ? null : Number(value))}
                  options={[
                    { value: 'default', label: defaultModel ? `默认：${defaultModel.name}` : '项目默认模型' },
                    ...models.map((model) => ({ value: model.id, label: model.name })),
                  ]}
                />
              </div>
              {/* 报错日志输入（Agent 模式） */}
              {mode === 'agent' && (
                <div className="mb-3">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-xs text-surface-muted">
                      <FileTextOutlined /> 错误日志（可选 - Agent 模式支持错误日志分析）
                    </span>
                    <button
                      type="button"
                      className="text-xs text-primary-400 hover:text-primary-300"
                      onClick={() => setShowErrorLog(!showErrorLog)}
                    >
                      {showErrorLog ? '收起' : '展开'}
                    </button>
                  </div>
                  {showErrorLog && (
                    <TextArea
                      value={errorLog}
                      onChange={(e) => setErrorLog(e.target.value)}
                      placeholder="粘贴完整的错误堆栈..."
                      rows={4}
                      className="!bg-surface-bg !border-surface-border !font-mono !text-xs"
                    />
                  )}
                </div>
              )}

              {/* 主输入框 */}
              <div className="flex gap-3">
                <TextArea
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                      e.preventDefault()
                      handleSend()
                    }
                  }}
                  placeholder={
                    mode === 'agent'
                      ? '描述你的问题或粘贴报错日志... (Enter 发送，Shift+Enter 换行)'
                      : '输入你的代码相关问题... (Enter 发送，Shift+Enter 换行)'
                  }
                  autoSize={{ minRows: 1, maxRows: 4 }}
                  disabled={isStreaming}
                  className="!bg-surface-bg !border-surface-border !resize-none"
                />
                {isStreaming ? (
                  <Button
                    danger
                    onClick={handleStop}
                    className="!h-auto !px-5"
                  >
                    停止
                  </Button>
                ) : (
                  <Button
                    type="primary"
                    icon={<SendOutlined />}
                    onClick={handleSend}
                    disabled={!input.trim()}
                    className="!h-auto !px-5 !bg-gradient-to-r !from-primary-500 !to-blue-600 !border-0"
                  >
                    发送
                  </Button>
                )}
              </div>
            </div>
          </div>
        </Content>
      </Layout>
    </Layout>
  )
}
