/**
 * API 客户端 - axios 封装 + SSE 支持
 */
import axios from 'axios'

const API_BASE = '/api/v1'

const http = axios.create({
  baseURL: API_BASE,
  timeout: 60000,
})

// 请求拦截器：添加 Token
http.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// 响应拦截器：处理 401
http.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error.response?.status
    const url = error.config?.url || '(unknown)'
    const method = error.config?.method?.toUpperCase() || '(unknown)'
    console.error(`[API ERROR] ${method} ${url} → ${status}`, error.response?.data || error.message)

    if (status === 401) {
      console.warn('[AUTH] 收到 401，清除 token 并跳转到登录页')
      localStorage.removeItem('access_token')
      localStorage.removeItem('user_info')
      window.location.href = '/login'
    }
    return Promise.reject(error)
  },
)

// ============ 认证 API ============
export const authApi = {
  login: (username: string, password: string) =>
    http.post('/auth/login', { username, password }).then((r) => r.data),

  // 普通用户自助注册
  register: (data: { username: string; email: string; password: string; full_name?: string }) =>
    http.post('/auth/register', data).then((r) => r.data),

  getMe: () => http.get('/auth/me').then((r) => r.data),

  // 管理员用户管理
  adminListUsers: () => http.get('/auth/admin/users').then((r) => r.data),

  adminCreateUser: (data: {
    username: string; email: string; password: string;
    full_name?: string; role?: 'admin' | 'developer';
  }) => http.post('/auth/admin/users', data).then((r) => r.data),

  adminUpdateUser: (id: number, data: {
    email?: string; full_name?: string;
    role?: 'admin' | 'developer'; is_active?: boolean;
  }) => http.put(`/auth/admin/users/${id}`, data).then((r) => r.data),

  adminResetPassword: (id: number, newPassword: string) =>
    http.post(`/auth/admin/users/${id}/reset-password`, { new_password: newPassword }).then((r) => r.data),

  adminDeleteUser: (id: number) =>
    http.delete(`/auth/admin/users/${id}`).then((r) => r.data),
}

// ============ 仓库 API ============
export const repoApi = {
  list: () => http.get('/repositories').then((r) => r.data),

  get: (id: number) => http.get(`/repositories/${id}`).then((r) => r.data),

  create: (data: any) => http.post('/repositories', data).then((r) => r.data),

  update: (id: number, data: any) =>
    http.put(`/repositories/${id}`, data).then((r) => r.data),

  delete: (id: number) =>
    http.delete(`/repositories/${id}`).then((r) => r.data),

  sync: (id: number) =>
    http.post(`/repositories/${id}/sync`).then((r) => r.data),

  listPermissions: (repoId: number) =>
    http.get(`/repositories/${repoId}/permissions`).then((r) => r.data),

  grantPermission: (repoId: number, data: any) =>
    http.post(`/repositories/${repoId}/permissions`, data).then((r) => r.data),

  revokePermission: (repoId: number, userId: number) =>
    http.delete(`/repositories/${repoId}/permissions/${userId}`).then((r) => r.data),
}

// ============ 对话 API ============
export interface ModelProvider {
  id: string
  name: string
  base_url: string
  models: string[]
  requires_api_key: boolean
  description: string
  docs_url: string
}

export interface ModelProfile {
  id: number
  name: string
  provider: string
  base_url: string
  model: string
  has_api_key: boolean
  is_default: boolean
}

export interface ModelInput {
  name: string
  provider: string
  base_url: string
  model: string
  api_key?: string
  is_default: boolean
}

export const modelApi = {
  providers: (): Promise<ModelProvider[]> => http.get('/models/providers').then((r) => r.data),
  list: (): Promise<ModelProfile[]> => http.get('/models').then((r) => r.data),
  create: (data: ModelInput) => http.post('/models', data).then((r) => r.data),
  update: (id: number, data: ModelInput) => http.put(`/models/${id}`, data).then((r) => r.data),
  remove: (id: number) => http.delete(`/models/${id}`),
  setDefault: (id: number) => http.post(`/models/${id}/default`).then((r) => r.data),
  test: (id: number) => http.post(`/models/${id}/test`, undefined, { timeout: 120000 }).then((r) => r.data),
  testDraft: (data: ModelInput, id?: number) => http.post('/models/test-connection', data, { params: { model_id: id }, timeout: 120000 }).then((r) => r.data),
  discover: (data: ModelInput, id?: number): Promise<{ models: string[] }> => http.post('/models/discover', data, { params: { model_id: id } }).then((r) => r.data),
}

export const chatApi = {
  ask: (data: any) => http.post('/chat/ask', data).then((r) => r.data),

  // SSE 流式接口
  stream: (
    query: string,
    mode: 'rag' | 'agent',
    repoIds: number[],
    conversationId: number | undefined,
    onEvent: (event: SSEEvent) => void,
    modelId?: number,
    errorLog?: string,
  ): (() => void) => {
    const token = localStorage.getItem('access_token')
    const controller = new AbortController()

    fetch(`${API_BASE}/chat/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: token ? `Bearer ${token}` : '',
      },
      body: JSON.stringify({ query, mode, repo_ids: repoIds, conversation_id: conversationId, model_id: modelId, error_log: errorLog }),
      signal: controller.signal,
    })
      .then(async (response) => {
        if (!response.ok || !response.body) {
          const detail = await response.json().catch(() => null)
          throw new Error(typeof detail?.detail === 'string' ? detail.detail : `请求失败 (HTTP ${response.status})`)
        }

        const reader = response.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''

        while (true) {
          const { value, done } = await reader.read()
          if (done) break

          buffer += decoder.decode(value, { stream: true })

          // 按 SSE 事件边界分割
          const events = buffer.split('\n\n')
          buffer = events.pop() || '' // 保留未完成的事件

          for (const rawEvent of events) {
            const event = parseSSEEvent(rawEvent)
            if (event) {
              onEvent(event)
            }
          }
        }

        // 处理缓冲区中剩余的事件
        if (buffer.trim()) {
          const event = parseSSEEvent(buffer)
          if (event) onEvent(event)
        }
      })
      .catch((err) => {
        if (err.name !== 'AbortError') {
          onEvent({ type: 'error', data: { message: err.message } })
        }
      })

    // 返回取消函数
    return () => controller.abort()
  },

  createConversation: (data: any) =>
    http.post('/chat/conversations', data).then((r) => r.data),

  listConversations: () =>
    http.get('/chat/conversations').then((r) => r.data),

  getMessages: (convId: number) =>
    http.get(`/chat/conversations/${convId}/messages`).then((r) => r.data),

  deleteConversation: (convId: number) =>
    http.delete(`/chat/conversations/${convId}`).then((r) => r.data),

  runCode: (code: string) =>
    http.post('/chat/run-code', null, { params: { code } }).then((r) => r.data),

  analyzeError: (errorLog: string, question?: string) =>
    http.post('/chat/analyze-error', { error_log: errorLog, question }).then((r) => r.data),
}

// ============ 健康检查 ============
export const healthApi = {
  check: () => http.get('/health').then((r) => r.data),
}

// ============ SSE 解析 ============
export interface SSEEvent {
  type: 'sources' | 'token' | 'thinking' | 'agent_step' | 'done' | 'error'
  data: any
  id?: string
}

function parseSSEEvent(raw: string): SSEEvent | null {
  const lines = raw.split('\n')
  let eventType = 'message'
  let dataStr = ''
  let id: string | undefined

  for (const line of lines) {
    if (!line.trim() || line.startsWith(':')) continue

    if (line.startsWith('event:')) {
      eventType = line.slice(6).trim()
    } else if (line.startsWith('data:')) {
      dataStr += line.slice(5).trim() + '\n'
    } else if (line.startsWith('id:')) {
      id = line.slice(3).trim()
    }
  }

  if (!dataStr.trim()) return null

  let data: any = dataStr.trim()
  // 尝试 JSON 解析
  try {
    data = JSON.parse(data)
  } catch {
    // 保持为字符串
  }

  return { type: eventType as SSEEvent['type'], data, id }
}

export default http
