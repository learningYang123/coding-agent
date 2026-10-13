import { Button, Dropdown } from 'antd'
import { LogoutOutlined, LoginOutlined, UserOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '@/store'

export default function AccountMenu() {
  const navigate = useNavigate()
  const { user, token, logout } = useAuthStore()

  if (!token) {
    return <Button icon={<LoginOutlined />} onClick={() => navigate('/login')}>登录</Button>
  }

  return (
    <Dropdown trigger={['click']} menu={{
      items: [
        { key: 'login', icon: <LoginOutlined />, label: '打开登录页' },
        { key: 'logout', icon: <LogoutOutlined />, label: '退出登录', danger: true },
      ],
      onClick: ({ key }) => {
        if (key === 'logout') logout()
        navigate('/login')
      },
    }}>
      <Button aria-label="账号菜单" icon={<UserOutlined />} className="!bg-surface-card !border-surface-border">
        <span className="max-w-24 truncate">{user?.username || '账号'}</span>
      </Button>
    </Dropdown>
  )
}
