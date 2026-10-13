import { useEffect, useState } from 'react'
import { Layout, Button, Table, Tag, Modal, Form, Input, Select, Space, message, Badge, Progress, Popconfirm, Tabs, Card } from 'antd'
import {
  CodeOutlined,
  PlusOutlined,
  SyncOutlined,
  DeleteOutlined,
  SettingOutlined,
  ArrowLeftOutlined,
  SearchOutlined,
  TeamOutlined,
} from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { repoApi, authApi } from '@/api/client'
import { useAuthStore } from '@/store'

const { Header, Content } = Layout

const statusConfig = {
  pending: { color: 'default', text: '待处理' },
  indexing: { color: 'processing', text: '索引中' },
  ready: { color: 'success', text: '就绪' },
  error: { color: 'error', text: '错误' },
}

export default function ReposPage() {
  const navigate = useNavigate()
  const user = useAuthStore((s) => s.user)
  const [repos, setRepos] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [createOpen, setCreateOpen] = useState(false)
  const [permOpen, setPermOpen] = useState(false)
  const [selectedRepo, setSelectedRepo] = useState<any>(null)
  const [users, setUsers] = useState<any[]>([])
  const [permissions, setPermissions] = useState<any[]>([])
  const [form] = Form.useForm()
  const [permForm] = Form.useForm()

  const loadRepos = async () => {
    setLoading(true)
    try {
      const data = await repoApi.list()
      setRepos(data)
    } catch (err) {
      message.error('加载仓库失败')
    } finally {
      setLoading(false)
    }
  }

  const loadUsers = async () => {
    if (!user || user.role !== 'admin') return
    try {
      const data = await authApi.adminListUsers()
      setUsers(data)
    } catch {}
  }

  useEffect(() => {
    loadRepos()
    loadUsers()
  }, [])

  const handleCreate = async () => {
    try {
      const values = await form.validateFields()
      await repoApi.create(values)
      message.success('仓库创建成功')
      form.resetFields()
      setCreateOpen(false)
      loadRepos()
    } catch (err: any) {
      message.error(err?.response?.data?.detail || '创建失败')
    }
  }

  const handleSync = async (repo: any) => {
    Modal.confirm({
      title: '同步仓库',
      content: `确定要同步/索引 "${repo.name}" 吗？这可能需要一些时间。`,
      onOk: async () => {
        try {
          await repoApi.sync(repo.id)
          message.success('同步完成')
          loadRepos()
        } catch (err: any) {
          message.error(err?.response?.data?.detail || '同步失败')
          loadRepos()
        }
      },
    })
  }

  const handleDelete = async (repo: any) => {
    try {
      await repoApi.delete(repo.id)
      message.success('删除成功')
      loadRepos()
    } catch (err: any) {
      message.error(err?.response?.data?.detail || '删除失败')
    }
  }

  const handleOpenPerm = async (repo: any) => {
    setSelectedRepo(repo)
    try {
      const data = await repoApi.listPermissions(repo.id)
      setPermissions(data)
    } catch {}
    setPermOpen(true)
  }

  const handleGrantPerm = async () => {
    try {
      const values = await permForm.validateFields()
      await repoApi.grantPermission(selectedRepo.id, {
        user_id: values.user_id,
        can_read: values.can_read ?? true,
        can_write: values.can_write ?? false,
      })
      message.success('权限已更新')
      permForm.resetFields()
      const data = await repoApi.listPermissions(selectedRepo.id)
      setPermissions(data)
    } catch {}
  }

  const languageTags = (languages: string) => {
    if (!languages) return null
    return languages.split(',').map((lang) => (
      <Tag key={lang} color="blue">{lang.trim()}</Tag>
    ))
  }

  const columns = [
    {
      title: '名称',
      dataIndex: 'name',
      key: 'name',
      render: (name: string) => <span className="font-medium">{name}</span>,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (status: string) => {
        const cfg: any = statusConfig[status as keyof typeof statusConfig] || statusConfig.pending
        return <Badge status={cfg.color} text={cfg.text} />
      },
    },
    {
      title: '语言',
      dataIndex: 'languages',
      key: 'languages',
      render: (langs: string) => languageTags(langs),
    },
    {
      title: '文件数',
      dataIndex: 'total_files',
      key: 'total_files',
      sorter: (a: any, b: any) => a.total_files - b.total_files,
    },
    {
      title: '代码块数',
      dataIndex: 'total_chunks',
      key: 'total_chunks',
      sorter: (a: any, b: any) => a.total_chunks - b.total_chunks,
    },
    {
      title: 'Git URL',
      dataIndex: 'git_url',
      key: 'git_url',
      render: (url: string) => (
        <span className="text-xs text-surface-muted truncate block max-w-[200px]">{url || '-'}</span>
      ),
    },
    {
      title: '操作',
      key: 'actions',
      render: (_: any, record: any) => (
        <Space size="small">
          <Button
            size="small"
            type="link"
            icon={<SyncOutlined />}
            onClick={() => handleSync(record)}
          >
            同步
          </Button>
          {user?.role === 'admin' && (
            <>
              <Button
                size="small"
                type="link"
                icon={<TeamOutlined />}
                onClick={() => handleOpenPerm(record)}
              >
                权限
              </Button>
              <Popconfirm
                title="确定删除这个仓库吗？"
                description="这将同时删除所有相关的向量数据"
                onConfirm={() => handleDelete(record)}
              >
                <Button size="small" type="link" danger icon={<DeleteOutlined />}>
                  删除
                </Button>
              </Popconfirm>
            </>
          )}
        </Space>
      ),
    },
  ]

  return (
    <Layout className="min-h-screen tech-bg">
      <Header className="!h-14 !bg-surface-card/80 backdrop-blur border-b border-surface-border flex items-center justify-between px-4">
        <div className="flex items-center gap-4">
          <Button
            type="text"
            icon={<ArrowLeftOutlined />}
            onClick={() => navigate('/')}
            className="!text-surface-text"
          />
          <CodeOutlined className="text-primary-500 text-xl" />
          <h2 className="text-base font-medium">仓库管理</h2>
        </div>

        {user?.role === 'admin' && (
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => {
              form.resetFields()
              setCreateOpen(true)
            }}
            className="!bg-gradient-to-r !from-primary-500 !to-blue-600 !border-0"
          >
            新建设仓库
          </Button>
        )}
      </Header>

      <Content className="p-6 max-w-7xl mx-auto w-full">
        <Card className="!bg-surface-card/60 !border-surface-border">
          <Table
            rowKey="id"
            columns={columns}
            dataSource={repos}
            loading={loading}
            pagination={false}
            className="!bg-transparent"
          />
        </Card>

        {/* 创建仓库弹窗 */}
        <Modal
          title="新建设仓库"
          open={createOpen}
          onCancel={() => setCreateOpen(false)}
          onOk={handleCreate}
          okText="创建"
          cancelText="取消"
        >
          <Form form={form} layout="vertical">
            <Form.Item name="name" label="仓库名称" rules={[{ required: true }]}>
              <Input placeholder="如：order-service" />
            </Form.Item>
            <Form.Item name="description" label="描述">
              <Input.TextArea rows={2} placeholder="仓库描述（可选）" />
            </Form.Item>
            <Form.Item name="git_url" label="Git URL">
              <Input placeholder="https://github.com/xxx/xxx.git（可选，也可以手动同步）" />
            </Form.Item>
            <Form.Item name="local_path" label="本地路径">
              <Input placeholder="D:/projects/my-repo（可选，优先使用）" />
            </Form.Item>
            <Form.Item name="default_branch" label="默认分支" initialValue="main">
              <Input placeholder="main / master" />
            </Form.Item>
          </Form>
        </Modal>

        {/* 权限管理弹窗 */}
        <Modal
          title={`权限管理 - ${selectedRepo?.name || ''}`}
          open={permOpen}
          onCancel={() => setPermOpen(false)}
          footer={null}
          width={600}
        >
          <div className="mb-4">
            <p className="text-sm text-surface-muted mb-2">添加用户权限</p>
            <Form form={permForm} layout="inline" onFinish={handleGrantPerm}>
              <Form.Item name="user_id" rules={[{ required: true }]}>
                <Select
                  placeholder="选择用户"
                  options={users.map((u) => ({ label: `${u.username} (${u.email})`, value: u.id }))}
                  style={{ width: 200 }}
                  showSearch
                  filterOption={(input, option) =>
                    (option?.label || '').toLowerCase().includes(input.toLowerCase())
                  }
                />
              </Form.Item>
              <Form.Item name="can_read" initialValue={true} valuePropName="checked">
                <Select options={[{ label: '可读', value: true }, { label: '不可读', value: false }]} style={{ width: 80 }} />
              </Form.Item>
              <Form.Item name="can_write" initialValue={false} valuePropName="checked">
                <Select options={[{ label: '可写', value: true }, { label: '不可写', value: false }]} style={{ width: 80 }} />
              </Form.Item>
              <Form.Item>
                <Button type="primary" htmlType="submit">授予</Button>
              </Form.Item>
            </Form>
          </div>

          <div className="border-t border-surface-border pt-4">
            <p className="text-sm text-surface-muted mb-2">当前权限</p>
            {permissions.length === 0 ? (
              <p className="text-center text-surface-muted py-4">暂无权限记录</p>
            ) : (
              <div className="space-y-2">
                {permissions.map((p) => {
                  const u = users.find((x) => x.id === p.user_id)
                  return (
                    <div key={p.id} className="flex items-center justify-between p-3 rounded-lg bg-surface-bg/50 border border-surface-border">
                      <span>{u?.username || `用户 #${p.user_id}`}</span>
                      <div className="flex items-center gap-2 text-xs">
                        {p.can_read && <Tag color="blue">可读</Tag>}
                        {p.can_write && <Tag color="green">可写</Tag>}
                        <Popconfirm
                          title="确认撤销？"
                          onConfirm={async () => {
                            await repoApi.revokePermission(p.repo_id, p.user_id)
                            const data = await repoApi.listPermissions(p.repo_id)
                            setPermissions(data)
                          }}
                        >
                          <Button size="small" type="link" danger>撤销</Button>
                        </Popconfirm>
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        </Modal>
      </Content>
    </Layout>
  )
}
