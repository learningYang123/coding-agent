import { useState } from 'react'
import { Form, Input, Button, message } from 'antd'
import { CodeOutlined, UserOutlined, LockOutlined, MailOutlined, ArrowLeftOutlined } from '@ant-design/icons'
import { Link, useNavigate } from 'react-router-dom'
import { authApi } from '@/api/client'

export default function RegisterPage() {
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()

  const handleRegister = async (values: {
    username: string
    email: string
    password: string
    full_name?: string
  }) => {
    setLoading(true)
    try {
      await authApi.register(values)
      message.success('注册成功，请登录')
      navigate('/login')
    } catch (err: any) {
      message.error(err?.response?.data?.detail || '注册失败')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="relative min-h-screen flex items-center justify-center tech-bg overflow-hidden">
      <div className="particles-bg" />
      <div className="absolute inset-0 bg-grid-pattern opacity-30" />

      <div className="relative z-10 w-full max-w-md mx-4">
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-gradient-to-br from-primary-500 to-purple-600 mb-4 shadow-lg shadow-primary-500/30">
            <CodeOutlined className="text-3xl text-white" />
          </div>
          <h1 className="text-2xl font-bold text-surface-text mb-2">注册新账号</h1>
          <p className="text-surface-muted">加入企业代码智能助手</p>
        </div>

        <div className="glass-card p-8">
          <Form
            size="large"
            layout="vertical"
            onFinish={handleRegister}
          >
            <Form.Item
              name="username"
              rules={[
                { required: true, message: '请输入用户名' },
                { min: 3, max: 64, message: '用户名长度 3-64 位' },
              ]}
            >
              <Input
                prefix={<UserOutlined className="text-surface-muted" />}
                placeholder="用户名"
                className="!bg-surface-bg/50 !border-surface-border"
              />
            </Form.Item>

            <Form.Item
              name="email"
              rules={[
                { required: true, message: '请输入邮箱' },
                { type: 'email', message: '邮箱格式不正确' },
              ]}
            >
              <Input
                prefix={<MailOutlined className="text-surface-muted" />}
                placeholder="邮箱"
                className="!bg-surface-bg/50 !border-surface-border"
              />
            </Form.Item>

            <Form.Item
              name="full_name"
            >
              <Input
                placeholder="真实姓名（可选）"
                className="!bg-surface-bg/50 !border-surface-border"
              />
            </Form.Item>

            <Form.Item
              name="password"
              rules={[
                { required: true, message: '请输入密码' },
                { min: 6, message: '密码至少 6 位' },
              ]}
            >
              <Input.Password
                prefix={<LockOutlined className="text-surface-muted" />}
                placeholder="密码（至少 6 位）"
                className="!bg-surface-bg/50 !border-surface-border"
              />
            </Form.Item>

            <Form.Item
              name="confirm_password"
              dependencies={['password']}
              rules={[
                { required: true, message: '请再次输入密码' },
                ({ getFieldValue }) => ({
                  validator(_, value) {
                    if (!value || getFieldValue('password') === value) {
                      return Promise.resolve()
                    }
                    return Promise.reject(new Error('两次密码输入不一致'))
                  },
                }),
              ]}
            >
              <Input.Password
                prefix={<LockOutlined className="text-surface-muted" />}
                placeholder="确认密码"
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
                {loading ? '注册中...' : '立即注册'}
              </Button>
            </Form.Item>

            <div className="text-center">
              <Link
                to="/login"
                className="!text-surface-muted hover:!text-primary-400 !text-sm inline-flex items-center gap-1"
              >
                <ArrowLeftOutlined /> 已有账号？返回登录
              </Link>
            </div>
          </Form>
        </div>

        <div className="text-center mt-6 text-xs text-surface-muted">
          <p>© 2026 企业代码智能助手</p>
        </div>
      </div>
    </div>
  )
}
