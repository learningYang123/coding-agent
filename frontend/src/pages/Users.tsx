import { useEffect, useState } from 'react'
import {
  Table, Button, Space, Tag, Modal, Form, Input, Select, Switch,
  message, Popconfirm, Card, Typography, Divider, Input as AntInput,
} from 'antd'
import {
  PlusOutlined, EditOutlined, DeleteOutlined, ReloadOutlined,
  KeyOutlined, SearchOutlined, UserOutlined, TeamOutlined,
  ArrowLeftOutlined,
} from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { authApi } from '@/api/client'
import { useAuthStore } from '@/store'

const { Title } = Typography

interface User {
  id: number
  username: string
  email: string
  full_name?: string
  role: 'admin' | 'developer'
  is_active: boolean
  avatar_url?: string | null
  created_at: string
  updated_at?: string | null
}

export default function UsersPage() {
  const navigate = useNavigate()
  const currentUser = useAuthStore((s) => s.user)
  const [users, setUsers] = useState<User[]>([])
  const [loading, setLoading] = useState(false)
  const [searchText, setSearchText] = useState('')
  const [roleFilter, setRoleFilter] = useState<string | undefined>(undefined)

  // 弹窗状态
  const [createOpen, setCreateOpen] = useState(false)
  const [editOpen, setEditOpen] = useState(false)
  const [resetPwdOpen, setResetPwdOpen] = useState(false)
  const [targetUser, setTargetUser] = useState<User | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const [createForm] = Form.useForm()
  const [editForm] = Form.useForm()
  const [resetPwdForm] = Form.useForm()

  const loadUsers = async () => {
    setLoading(true)
    try {
      const list = await authApi.adminListUsers()
      setUsers(list)
    } catch (err: any) {
      message.error(err?.response?.data?.detail || '加载用户列表失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadUsers() }, [])

  // 过滤
  const filtered = users.filter((u) => {
    const matchSearch =
      !searchText ||
      u.username.toLowerCase().includes(searchText.toLowerCase()) ||
      u.email.toLowerCase().includes(searchText.toLowerCase()) ||
      (u.full_name || '').toLowerCase().includes(searchText.toLowerCase())
    const matchRole = !roleFilter || u.role === roleFilter
    return matchSearch && matchRole
  })

  // ====== 创建 ======
  const openCreate = () => {
    createForm.resetFields()
    setCreateOpen(true)
  }

  const handleCreate = async () => {
    const values = await createForm.validateFields()
    setSubmitting(true)
    try {
      await authApi.adminCreateUser(values)
      message.success('用户创建成功')
      setCreateOpen(false)
      loadUsers()
    } catch (err: any) {
      message.error(err?.response?.data?.detail || '创建失败')
    } finally {
      setSubmitting(false)
    }
  }

  // ====== 编辑 ======
  const openEdit = (user: User) => {
    setTargetUser(user)
    editForm.setFieldsValue({
      email: user.email,
      full_name: user.full_name,
      role: user.role,
      is_active: user.is_active,
    })
    setEditOpen(true)
  }

  const handleEdit = async () => {
    if (!targetUser) return
    const values = await editForm.validateFields()
    setSubmitting(true)
    try {
      await authApi.adminUpdateUser(targetUser.id, values)
      message.success('用户信息已更新')
      setEditOpen(false)
      loadUsers()
    } catch (err: any) {
      message.error(err?.response?.data?.detail || '更新失败')
    } finally {
      setSubmitting(false)
    }
  }

  // ====== 重置密码 ======
  const openResetPwd = (user: User) => {
    setTargetUser(user)
    resetPwdForm.resetFields()
    setResetPwdOpen(true)
  }

  const handleResetPwd = async () => {
    if (!targetUser) return
    const values = await resetPwdForm.validateFields()
    setSubmitting(true)
    try {
      await authApi.adminResetPassword(targetUser.id, values.new_password)
      message.success('密码已重置')
      setResetPwdOpen(false)
    } catch (err: any) {
      message.error(err?.response?.data?.detail || '重置密码失败')
    } finally {
      setSubmitting(false)
    }
  }

  // ====== 删除 ======
  const handleDelete = async (user: User) => {
    try {
      await authApi.adminDeleteUser(user.id)
      message.success('用户已删除')
      loadUsers()
    } catch (err: any) {
      message.error(err?.response?.data?.detail || '删除失败')
    }
  }

  // ====== 启禁用快捷切换 ======
  const toggleActive = async (user: User) => {
    try {
      await authApi.adminUpdateUser(user.id, { is_active: !user.is_active })
      message.success(user.is_active ? '已禁用' : '已启用')
      loadUsers()
    } catch (err: any) {
      message.error(err?.response?.data?.detail || '操作失败')
    }
  }

  const columns = [
    {
      title: 'ID',
      dataIndex: 'id',
      width: 60,
    },
    {
      title: '用户名',
      dataIndex: 'username',
      width: 140,
      render: (v: string, r: User) => (
        <span className="font-medium">
          {v}
          {r.id === currentUser?.id && (
            <Tag color="blue" className="ml-1 !mb-0">我</Tag>
          )}
        </span>
      ),
    },
    {
      title: '邮箱',
      dataIndex: 'email',
      width: 200,
    },
    {
      title: '姓名',
      dataIndex: 'full_name',
      width: 140,
      render: (v?: string) => v || <span className="text-surface-muted">-</span>,
    },
    {
      title: '角色',
      dataIndex: 'role',
      width: 110,
      render: (role: string) =>
        role === 'admin' ? (
          <Tag color="gold" icon={<TeamOutlined />}>管理员</Tag>
        ) : (
          <Tag color="blue" icon={<UserOutlined />}>开发者</Tag>
        ),
    },
    {
      title: '状态',
      dataIndex: 'is_active',
      width: 120,
      render: (active: boolean, r: User) => (
        <div className="flex items-center gap-2">
          <Switch
            size="small"
            checked={active}
            disabled={r.id === currentUser?.id}
            onChange={() => toggleActive(r)}
          />
          {active ? (
            <span className="text-green-400 text-xs">启用</span>
          ) : (
            <span className="text-red-400 text-xs">禁用</span>
          )}
        </div>
      ),
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      width: 180,
      render: (v: string) => v ? new Date(v).toLocaleString('zh-CN') : '-',
    },
    {
      title: '操作',
      key: 'action',
      width: 260,
      fixed: 'right' as const,
      render: (_: any, r: User) => (
        <Space size={4}>
          <Button
            size="small"
            type="link"
            icon={<EditOutlined />}
            onClick={() => openEdit(r)}
          >
            编辑
          </Button>
          <Button
            size="small"
            type="link"
            icon={<KeyOutlined />}
            onClick={() => openResetPwd(r)}
          >
            重置密码
          </Button>
          <Popconfirm
            title={`确定删除用户 "${r.username}" 吗？`}
            okText="删除"
            okType="danger"
            cancelText="取消"
            onConfirm={() => handleDelete(r)}
            disabled={r.id === currentUser?.id}
          >
            <Button
              size="small"
              type="link"
              danger
              icon={<DeleteOutlined />}
              disabled={r.id === currentUser?.id}
            >
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <div className="min-h-screen bg-surface-bg p-6">
      <div className="max-w-7xl mx-auto">
        {/* 顶部 */}
        <div className="flex items-center justify-between mb-6">
          <Space>
            <Button
              icon={<ArrowLeftOutlined />}
              onClick={() => navigate('/')}
              className="!border-surface-border"
            >
              返回聊天
            </Button>
            <Title level={3} style={{ margin: 0, color: '#fff' }}>
              <TeamOutlined className="mr-2" />用户管理
            </Title>
          </Space>
          <Space>
            <Button
              icon={<ReloadOutlined />}
              onClick={loadUsers}
              loading={loading}
            >
              刷新
            </Button>
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={openCreate}
            >
              新建用户
            </Button>
          </Space>
        </div>

        {/* 统计 + 搜索 */}
        <Card className="!bg-surface-card !border-surface-border mb-6">
          <div className="flex items-center gap-4 flex-wrap">
            <div className="text-sm text-surface-muted">
              共 <span className="text-primary-400 font-semibold">{users.length}</span> 位用户
              （管理员 {users.filter((u) => u.role === 'admin').length}，
              开发者 {users.filter((u) => u.role === 'developer').length}）
            </div>
            <div className="flex-1" />
            <AntInput
              allowClear
              prefix={<SearchOutlined className="text-surface-muted" />}
              placeholder="搜索用户名 / 邮箱 / 姓名"
              value={searchText}
              onChange={(e) => setSearchText(e.target.value)}
              style={{ width: 240 }}
              className="!bg-surface-bg/50 !border-surface-border"
            />
            <Select
              allowClear
              placeholder="全部角色"
              style={{ width: 120 }}
              value={roleFilter}
              onChange={setRoleFilter}
              options={[
                { value: 'admin', label: '管理员' },
                { value: 'developer', label: '开发者' },
              ]}
            />
          </div>
        </Card>

        {/* 表格 */}
        <Card className="!bg-surface-card !border-surface-border !p-0">
          <Table
            rowKey="id"
            loading={loading}
            columns={columns}
            dataSource={filtered}
            scroll={{ x: 1100 }}
            pagination={{
              pageSize: 10,
              showSizeChanger: true,
              showTotal: (t) => `共 ${t} 条`,
            }}
            className="surface-table"
          />
        </Card>
      </div>

      {/* ====== 创建用户弹窗 ====== */}
      <Modal
        title="新建用户"
        open={createOpen}
        onCancel={() => setCreateOpen(false)}
        onOk={handleCreate}
        confirmLoading={submitting}
        okText="创建"
        cancelText="取消"
      >
        <Form form={createForm} layout="vertical" className="mt-4">
          <Form.Item name="username" label="用户名" rules={[
            { required: true, message: '请输入用户名' },
            { min: 3, max: 64, message: '长度 3-64' },
          ]}>
            <Input placeholder="用户登录名" />
          </Form.Item>
          <Form.Item name="email" label="邮箱" rules={[
            { required: true, message: '请输入邮箱' },
            { type: 'email', message: '邮箱格式不正确' },
          ]}>
            <Input placeholder="user@example.com" />
          </Form.Item>
          <Form.Item name="full_name" label="姓名">
            <Input placeholder="可选" />
          </Form.Item>
          <Form.Item name="password" label="初始密码" rules={[
            { required: true, message: '请输入密码' },
            { min: 6, message: '至少 6 位' },
          ]}>
            <Input.Password placeholder="至少 6 位" />
          </Form.Item>
          <Form.Item name="role" label="角色" initialValue="developer">
            <Select
              options={[
                { value: 'developer', label: '开发者' },
                { value: 'admin', label: '管理员' },
              ]}
            />
          </Form.Item>
        </Form>
      </Modal>

      {/* ====== 编辑用户弹窗 ====== */}
      <Modal
        title={`编辑用户 - ${targetUser?.username}`}
        open={editOpen}
        onCancel={() => setEditOpen(false)}
        onOk={handleEdit}
        confirmLoading={submitting}
        okText="保存"
        cancelText="取消"
      >
        <Form form={editForm} layout="vertical" className="mt-4">
          <Form.Item name="email" label="邮箱" rules={[
            { type: 'email', message: '邮箱格式不正确' },
          ]}>
            <Input />
          </Form.Item>
          <Form.Item name="full_name" label="姓名">
            <Input />
          </Form.Item>
          <Form.Item name="role" label="角色">
            <Select
              options={[
                { value: 'developer', label: '开发者' },
                { value: 'admin', label: '管理员' },
              ]}
            />
          </Form.Item>
          <Form.Item name="is_active" label="账户状态" valuePropName="checked">
            <Switch checkedChildren="启用" unCheckedChildren="禁用" />
          </Form.Item>
        </Form>
      </Modal>

      {/* ====== 重置密码弹窗 ====== */}
      <Modal
        title={`重置密码 - ${targetUser?.username}`}
        open={resetPwdOpen}
        onCancel={() => setResetPwdOpen(false)}
        onOk={handleResetPwd}
        confirmLoading={submitting}
        okText="确认重置"
        cancelText="取消"
        okButtonProps={{ danger: true }}
      >
        <div className="text-sm text-surface-muted mb-4">
          重置后该用户需使用新密码重新登录。
        </div>
        <Form form={resetPwdForm} layout="vertical">
          <Form.Item name="new_password" label="新密码" rules={[
            { required: true, message: '请输入新密码' },
            { min: 6, message: '至少 6 位' },
          ]}>
            <Input.Password placeholder="至少 6 位" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
