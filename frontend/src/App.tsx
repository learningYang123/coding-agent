import { Routes, Route, Navigate } from 'react-router-dom'
import { useAuthStore } from '@/store'
import LoginPage from '@/pages/Login'
import RegisterPage from '@/pages/Register'
import ChatPage from '@/pages/Chat'
import ReposPage from '@/pages/Repos'
import UsersPage from '@/pages/Users'
import ModelsPage from '@/pages/Models'
import { useEffect } from 'react'
import { authApi } from '@/api/client'
import { message } from 'antd'

function App() {
  const token = useAuthStore((s) => s.token)
  const setUser = useAuthStore((s) => s.setUser)
  const logout = useAuthStore((s) => s.logout)

  // 应用启动时验证 token
  useEffect(() => {
    if (token) {
      console.log('[App] 启动，验证已有 token...')
      authApi
        .getMe()
        .then((user) => {
          console.log('[App] /me 成功, role=', user.role)
          setUser(user)
        })
        .catch((e) => {
          console.error('[App] /me 失败，执行 logout:', e?.response?.status || e?.message)
          logout()
          message.error('登录已过期，请重新登录')
        })
    }
  }, [])

  if (!token) {
    return (
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    )
  }

  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route path="/" element={<ChatPage />} />
      <Route path="/chat" element={<ChatPage />} />
      <Route path="/repos" element={<ReposPage />} />
      <Route path="/users" element={<UsersPage />} />
      <Route path="/models" element={<ModelsPage />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

export default App
