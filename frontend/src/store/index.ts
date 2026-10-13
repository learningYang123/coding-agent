/**
 * Zustand Store - 全局状态管理
 */
import { create } from 'zustand'
import { modelApi, ModelProfile } from '@/api/client'

// ============ 用户状态 ============
interface User {
  id: number
  username: string
  email: string
  full_name?: string
  role: 'admin' | 'developer'
  is_active: boolean
  avatar_url?: string
}

interface AuthState {
  token: string | null
  user: User | null
  setAuth: (token: string, user: User) => void
  setUser: (user: User) => void
  logout: () => void
  isAuthenticated: () => boolean
  isAdmin: () => boolean
}

export const useAuthStore = create<AuthState>((set, get) => ({
  token: localStorage.getItem('access_token'),
  user: (() => {
    const raw = localStorage.getItem('user_info')
    try { return raw ? JSON.parse(raw) : null } catch { return null }
  })(),

  setAuth: (token, user) => {
    if (get().user?.id !== user.id) clearAccountState()
    localStorage.setItem('access_token', token)
    localStorage.setItem('user_info', JSON.stringify(user))
    set({ token, user })
  },

  setUser: (user) => {
    localStorage.setItem('user_info', JSON.stringify(user))
    set({ user })
  },

  logout: () => {
    localStorage.removeItem('access_token')
    localStorage.removeItem('user_info')
    set({ token: null, user: null })
    clearAccountState()
  },

  isAuthenticated: () => !!get().token,
  isAdmin: () => get().user?.role === 'admin',
}))

// ============ 仓库状态 ============
interface Repo {
  id: number
  name: string
  description?: string
  git_url?: string
  languages?: string
  status: 'pending' | 'indexing' | 'ready' | 'error'
  total_files: number
  total_chunks: number
  is_public: boolean
  created_at: string
}

interface RepoState {
  repos: Repo[]
  selectedRepoIds: number[]
  loading: boolean
  setRepos: (repos: Repo[]) => void
  setSelectedRepos: (ids: number[]) => void
  toggleRepo: (id: number) => void
  clearSelection: () => void
}

export const useRepoStore = create<RepoState>((set) => ({
  repos: [],
  selectedRepoIds: [],
  loading: false,

  setRepos: (repos) => set({ repos }),

  setSelectedRepos: (ids) => set({ selectedRepoIds: ids }),

  toggleRepo: (id) =>
    set((state) => ({
      selectedRepoIds: state.selectedRepoIds.includes(id)
        ? state.selectedRepoIds.filter((r) => r !== id)
        : [...state.selectedRepoIds, id],
    })),

  clearSelection: () => set({ selectedRepoIds: [] }),
}))

// ============ 对话状态 ============
interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  sources?: any[]
  thinking?: string
  streaming?: boolean
  agentSteps?: { step: string; detail?: any }[]
}

interface Conversation {
  id: number
  title?: string
  mode: 'rag' | 'agent'
  repo_ids?: string
  created_at: string
  updated_at: string
}

interface ChatState {
  mode: 'rag' | 'agent'
  messages: ChatMessage[]
  conversations: Conversation[]
  currentConversationId: number | null
  isStreaming: boolean
  setMode: (mode: 'rag' | 'agent') => void
  setMessages: (msgs: ChatMessage[]) => void
  appendMessage: (msg: ChatMessage) => void
  updateLastAssistant: (updates: Partial<ChatMessage>) => void
  startStreaming: () => void
  stopStreaming: () => void
  clearMessages: () => void
  setConversations: (convs: Conversation[]) => void
  setCurrentConversation: (id: number | null) => void
}

export const useChatStore = create<ChatState>((set, get) => ({
  mode: 'rag',
  messages: [],
  conversations: [],
  currentConversationId: null,
  isStreaming: false,

  setMode: (mode) => set({ mode }),

  setMessages: (messages) => set({ messages }),

  appendMessage: (msg) => set((state) => ({ messages: [...state.messages, msg] })),

  updateLastAssistant: (updates) =>
    set((state) => {
      const msgs = [...state.messages]
      for (let i = msgs.length - 1; i >= 0; i--) {
        if (msgs[i].role === 'assistant' && msgs[i].streaming) {
          msgs[i] = { ...msgs[i], ...updates }
          break
        }
      }
      return { messages: msgs }
    }),

  startStreaming: () => set({ isStreaming: true }),
  stopStreaming: () => set({ isStreaming: false }),

  clearMessages: () => set({ messages: [], currentConversationId: null }),

  setConversations: (conversations) => set({ conversations }),

  setCurrentConversation: (id) => set({ currentConversationId: id }),
}))

interface ModelState {
  models: ModelProfile[]
  selectedModelId: number | null
  loading: boolean
  refresh: () => Promise<void>
  select: (id: number | null) => void
  reset: () => void
}

export const useModelStore = create<ModelState>((set, get) => ({
  models: [],
  selectedModelId: null,
  loading: false,
  refresh: async () => {
    const token = useAuthStore.getState().token
    set({ loading: true })
    try {
      const models = await modelApi.list()
      if (useAuthStore.getState().token !== token) return
      const selected = get().selectedModelId
      set({ models, selectedModelId: models.some((m) => m.id === selected) ? selected : null })
    } finally {
      if (useAuthStore.getState().token === token) set({ loading: false })
    }
  },
  select: (selectedModelId) => set({ selectedModelId }),
  reset: () => set({ models: [], selectedModelId: null, loading: false }),
}))

function clearAccountState() {
  useModelStore.getState().reset()
  useRepoStore.setState({ repos: [], selectedRepoIds: [], loading: false })
  useChatStore.setState({ messages: [], conversations: [], currentConversationId: null, isStreaming: false })
}
