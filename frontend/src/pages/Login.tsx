import { useState } from 'react'
import { Form, Input, Button, message } from 'antd'
import { CodeOutlined, UserOutlined, LockOutlined } from '@ant-design/icons'
import { Link, useNavigate } from 'react-router-dom'
import { authApi } from '@/api/client'
import { useAuthStore } from '@/store'

export default function LoginPage() {
  const [loading, setLoading] = useState(false)
  const setAuth = useAuthStore((s) => s.setAuth)
  const token = useAuthStore((s) => s.token)
  const navigate = useNavigate()

  const handleLogin = async (values: { username: string; password: string }) => {
    setLoading(true)
    try {
      const res = await authApi.login(values.username, values.password)
      setAuth(res.access_token, res.user)
      console.log('[Login] 登录成功, role=', res.user.role, ', 正在跳转...')
      message.success('登录成功')
      navigate('/', { replace: true })
    } catch (err: any) {
      console.error('[Login] 登录失败:', err?.response?.data?.detail || err?.message)
      message.error(err?.response?.data?.detail || '登录失败')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="relative min-h-screen flex items-center justify-center tech-bg overflow-hidden">
      {/* 背景装饰 */}
      <div className="particles-bg" />
      <div className="absolute inset-0 bg-grid-pattern opacity-30" />

      {/* 中心卡片 */}
      <div className="relative z-10 w-full max-w-md mx-4">
        {/* Logo 和标题 */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-gradient-to-br from-primary-500 to-purple-600 mb-4 shadow-lg shadow-primary-500/30">
            <CodeOutlined className="text-3xl text-white" />
          </div>
          <h1 className="text-2xl font-bold text-surface-text mb-2">企业代码智能助手</h1>
          <p className="text-surface-muted">RAG + Agent · 代码检索 · 智能排错</p>
        </div>

        {/* 登录表单 */}
        <div className="glass-card p-8">
          <Form
            size="large"
            layout="vertical"
            onFinish={handleLogin}
          >
            <Form.Item
              name="username"
              rules={[{ required: true, message: '请输入用户名' }]}
            >
              <Input
                prefix={<UserOutlined className="text-surface-muted" />}
                placeholder="用户名"
                autoComplete="username"
                className="!bg-surface-bg/50 !border-surface-border"
              />
            </Form.Item>

            <Form.Item
              name="password"
              rules={[{ required: true, message: '请输入密码' }]}
            >
              <Input.Password
                prefix={<LockOutlined className="text-surface-muted" />}
                placeholder="密码"
                autoComplete="current-password"
                className="!bg-surface-bg/50 !border-surface-border"
              />
            </Form.Item>

            <Form.Item className="!mb-2">
              <Button
                type="primary"
                htmlType="submit"
                loading={loading}
                block
                size="large"
                className="!h-11 !bg-gradient-to-r !from-primary-500 !to-blue-600 !border-0 hover:!opacity-90 transition-opacity"
              >
                {loading ? '登录中...' : '登录'}
              </Button>
            </Form.Item>

            {/* 注册入口 */}
            <div className="text-center !mb-4">
              <Link
                to="/register"
                className="!text-primary-400 hover:!text-primary-300 !text-sm"
              >
                没有账号？立即注册
              </Link>
            </div>
          </Form>

        </div>

        {/* 页脚 */}
        <div className="text-center mt-6 text-xs text-surface-muted">
          {token && <Link to="/" className="inline-block text-primary-400 mb-4 text-sm">返回已登录的工作台</Link>}
          <p>© 2026 企业代码智能助手 · Powered by LangChain + LangGraph</p>
        </div>
      </div>
    </div>
  )
}
