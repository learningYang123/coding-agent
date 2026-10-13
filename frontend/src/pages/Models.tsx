import { useEffect, useState } from 'react'
import { Alert, AutoComplete, Button, Empty, Form, Input, Modal, Popconfirm, Select, Spin, Switch, Tag, message } from 'antd'
import { ArrowLeftOutlined, CheckCircleOutlined, CloudOutlined, DeleteOutlined, EditOutlined, KeyOutlined, PlusOutlined, ReloadOutlined, RobotOutlined, StarOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { modelApi, ModelInput, ModelProfile, ModelProvider } from '@/api/client'
import { useModelStore } from '@/store'
import AccountMenu from '@/components/AccountMenu'

const errorMessage = (error: any) => typeof error?.response?.data?.detail === 'string' ? error.response.data.detail : '操作失败，请稍后重试'

export default function ModelsPage() {
  const navigate = useNavigate()
  const { models, loading, refresh } = useModelStore()
  const [providers, setProviders] = useState<ModelProvider[]>([])
  const [open, setOpen] = useState(false)
  const [editing, setEditing] = useState<ModelProfile | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [feedback, setFeedback] = useState<{ type: 'success' | 'error'; text: string } | null>(null)
  const [discovered, setDiscovered] = useState<string[]>([])
  const [loadError, setLoadError] = useState('')
  const [form] = Form.useForm<ModelInput>()
  const providerId = Form.useWatch('provider', form)
  const provider = providers.find((p) => p.id === providerId)
  const keepsKey = !!editing?.has_api_key && editing.provider === providerId

  const load = async () => {
    setLoadError('')
    try {
      const [catalog] = await Promise.all([modelApi.providers(), refresh()])
      setProviders(catalog)
    } catch (error) {
      setLoadError(errorMessage(error))
    }
  }

  useEffect(() => { void load() }, [])

  const showEditor = (profile?: ModelProfile) => {
    form.resetFields()
    setEditing(profile || null)
    setDiscovered([])
    setFeedback(null)
    const first = providers.find((p) => p.id === 'deepseek')
    form.setFieldsValue(profile ? {
      name: profile.name, provider: profile.provider, base_url: profile.base_url, model: profile.model, is_default: profile.is_default,
    } : {
      name: '', provider: first?.id, base_url: first?.base_url, model: first?.models[0], is_default: models.length === 0,
    })
    setOpen(true)
  }

  const changeProvider = (id: string) => {
    const preset = providers.find((p) => p.id === id)
    form.setFieldsValue({ base_url: preset?.base_url || '', model: preset?.models[0] || '', api_key: '' })
    setDiscovered([])
    setFeedback(null)
  }

  const draft = async (discovery = false): Promise<ModelInput> => {
    await form.validateFields(discovery ? ['provider', 'base_url', 'api_key'] : undefined)
    const values = form.getFieldsValue()
    const key = values.api_key?.trim()
    return {
      ...values,
      name: values.name?.trim() || `${provider?.name || '模型'} · ${values.model || '连接'}`,
      model: values.model?.trim() || '__discovery__',
      base_url: values.base_url.trim(),
      api_key: key || (keepsKey ? undefined : ''),
      is_default: !!values.is_default,
    }
  }

  const save = async () => {
    let values: ModelInput
    try { values = await draft() } catch { return }
    setBusy('save')
    try {
      if (editing) await modelApi.update(editing.id, values)
      else await modelApi.create(values)
      await refresh()
      setOpen(false)
      form.resetFields()
      message.success('模型配置已保存')
    } catch (error) {
      setFeedback({ type: 'error', text: errorMessage(error) })
    } finally { setBusy(null) }
  }

  const testDraft = async () => {
    let values: ModelInput
    try { values = await draft() } catch { return }
    setBusy('test-draft')
    setFeedback(null)
    try {
      const result = await modelApi.testDraft(values, editing?.id)
      setFeedback({ type: 'success', text: result.message })
    } catch (error) {
      setFeedback({ type: 'error', text: errorMessage(error) })
    } finally { setBusy(null) }
  }

  const discover = async () => {
    let values: ModelInput
    try { values = await draft(true) } catch { return }
    setBusy('discover')
    setFeedback(null)
    try {
      const result = await modelApi.discover(values, editing?.id)
      setDiscovered(result.models)
      if (result.models.length && !result.models.includes(form.getFieldValue('model'))) form.setFieldValue('model', result.models[0])
      setFeedback({ type: result.models.length ? 'success' : 'error', text: result.models.length ? `已获取 ${result.models.length} 个模型，请选择对话模型` : '服务未返回模型列表，请手动输入模型 ID' })
    } catch (error) {
      setFeedback({ type: 'error', text: errorMessage(error) })
    } finally { setBusy(null) }
  }

  const act = async (key: string, action: () => Promise<any>, success: string) => {
    setBusy(key)
    try {
      await action()
      await refresh()
      message.success(success)
    } catch (error) { message.error(errorMessage(error)) }
    finally { setBusy(null) }
  }

  const options = (discovered.length ? discovered : provider?.models || []).map((value) => ({ value }))

  return (
    <div className="min-h-screen tech-bg">
      <header className="bg-surface-card/80 backdrop-blur border-b border-surface-border px-4 md:px-8 py-3 flex items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <Button aria-label="返回聊天" icon={<ArrowLeftOutlined />} onClick={() => navigate('/')} />
          <span className="font-semibold text-base">模型设置</span>
        </div>
        <div className="flex items-center gap-2">
          <Button icon={<ReloadOutlined />} onClick={load} loading={loading}>刷新</Button>
          <AccountMenu />
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-4 md:px-8 py-6">
        <div className="flex flex-wrap justify-between gap-4 items-center mb-6">
          <div>
            <h1 className="text-xl font-semibold text-surface-text mb-2">模型连接</h1>
            <p className="text-sm text-surface-muted">添加云端、本地或中转模型，设置默认模型后即可用于对话。</p>
          </div>
          <Button type="primary" icon={<PlusOutlined />} disabled={!providers.length || !!busy} onClick={() => showEditor()}>添加模型</Button>
        </div>

        {loadError && <Alert type="error" showIcon message={loadError} className="mb-5" action={<Button size="small" onClick={load}>重试</Button>} />}
        <Spin spinning={loading}>
          {models.length === 0 ? (
            <div className="model-card py-12 text-center">
              <Empty description={<span className="text-surface-muted">还没有添加模型</span>} />
              <p className="text-sm text-surface-muted my-4">添加第一个模型后，它会自动成为默认模型。</p>
              <Button type="primary" disabled={!providers.length} onClick={() => showEditor()} icon={<PlusOutlined />}>添加第一个模型</Button>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
              {models.map((profile) => (
                <article key={profile.id} className={`model-card ${profile.is_default ? 'is-default' : ''}`}>
                  <div className="flex items-start justify-between gap-3 mb-4">
                    <div className="flex gap-3 min-w-0">
                      <div className="w-11 h-11 rounded-xl bg-primary-500/15 text-primary-400 flex items-center justify-center text-xl shrink-0"><RobotOutlined /></div>
                      <div className="min-w-0"><h2 className="font-semibold text-base truncate">{profile.name}</h2><p className="text-xs text-surface-muted mt-1">{providers.find((p) => p.id === profile.provider)?.name || profile.provider}</p></div>
                    </div>
                    {profile.is_default && <Tag color="blue" icon={<StarOutlined />}>默认</Tag>}
                  </div>
                  <p className="font-mono text-sm text-surface-text break-all mb-2">{profile.model}</p>
                  <p className="text-xs text-surface-muted break-all mb-4">{profile.base_url}</p>
                  <div className="text-xs text-surface-muted mb-5"><KeyOutlined /> {profile.has_api_key ? '密钥已保存' : '无需密钥 / 未设置密钥'}</div>
                  <div className="flex flex-wrap gap-2 pt-4 border-t border-surface-border">
                    <Button size="small" icon={<CheckCircleOutlined />} loading={busy === `test-${profile.id}`} disabled={!!busy && busy !== `test-${profile.id}`} onClick={() => act(`test-${profile.id}`, () => modelApi.test(profile.id), '连接成功，模型已返回响应')}>测试连接</Button>
                    <Button size="small" icon={<EditOutlined />} disabled={!!busy} onClick={() => showEditor(profile)}>编辑</Button>
                    {!profile.is_default && <Button size="small" disabled={!!busy} onClick={() => act(`default-${profile.id}`, () => modelApi.setDefault(profile.id), '默认模型已更新')}>设为默认</Button>}
                    <Popconfirm title="删除这个模型配置？" description="删除后需重新填写密钥才能添加。" onConfirm={() => act(`delete-${profile.id}`, () => modelApi.remove(profile.id), '模型已删除')} okText="删除" cancelText="取消">
                      <Button aria-label={`删除 ${profile.name}`} size="small" danger icon={<DeleteOutlined />} disabled={!!busy} />
                    </Popconfirm>
                  </div>
                </article>
              ))}
            </div>
          )}
        </Spin>
        <p className="text-xs text-surface-muted mt-6 leading-relaxed">未添加模型时沿用项目默认配置。模型可用性由服务商账户权限决定；“测试连接”会发送一条简短请求。</p>
      </main>

      <Modal title={editing ? '编辑模型' : '添加模型'} open={open} width={580} style={{ top: 24 }} styles={{ body: { maxHeight: 'calc(100dvh - 180px)', overflowY: 'auto', paddingRight: 8 } }} onCancel={() => { if (!busy) { setOpen(false); form.resetFields() } }} closable={!busy} maskClosable={!busy} destroyOnClose footer={[
        <Button key="cancel" disabled={!!busy} onClick={() => { setOpen(false); form.resetFields() }}>取消</Button>,
        <Button key="test" icon={<CheckCircleOutlined />} loading={busy === 'test-draft'} disabled={!!busy && busy !== 'test-draft'} onClick={testDraft}>测试连接</Button>,
        <Button key="save" type="primary" loading={busy === 'save'} disabled={!!busy && busy !== 'save'} onClick={save}>保存模型</Button>,
      ]}>
        <Form form={form} layout="vertical" className="mt-5" disabled={!!busy}>
          <Form.Item name="provider" label="供应商 / 平台" rules={[{ required: true, message: '请选择供应商' }]}>
            <Select options={providers.map((p) => ({ value: p.id, label: p.name }))} onChange={changeProvider} />
          </Form.Item>
          {provider && <Alert type="info" showIcon className="mb-5" message={provider.description} action={provider.docs_url ? <a className="text-primary-500 text-xs whitespace-nowrap" href={provider.docs_url} target="_blank" rel="noreferrer">官方文档</a> : undefined} />}
          <Form.Item name="name" label="显示名称" rules={[{ required: true, whitespace: true, message: '请输入显示名称' }]}>
            <Input placeholder="例如：日常编程 / 本地千问" maxLength={100} />
          </Form.Item>
          <Form.Item name="base_url" label="API 地址 (Base URL)" extra="填写基础地址，例如 https://api.openai.com/v1，可按地域或中转平台修改。" rules={[{ required: true, message: '请输入 API 地址' }, { validator: (_, value) => { try { const url = new URL(value); if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.search || url.hash || /[{}\s]/.test(value)) throw new Error(); return Promise.resolve() } catch { return Promise.reject(new Error('请输入有效的 http(s) 基础地址，不含密钥或占位符')) } } }]}>
            <Input placeholder="https://your-provider.example/v1" maxLength={512} />
          </Form.Item>
          <Form.Item name="api_key" label={provider?.requires_api_key ? 'API Key' : 'API Key（可选）'} extra={keepsKey ? '已有密钥，留空则保留；输入新密钥可替换。' : providerId === 'ollama' ? '本地 Ollama 通常无需密钥。' : '从所选平台控制台获取密钥。'} rules={[{ required: !!provider?.requires_api_key && !keepsKey, whitespace: true, message: '请输入该平台的 API Key' }]}>
            <Input.Password autoComplete="new-password" placeholder={keepsKey ? '已保存，留空保留' : '粘贴 API Key'} />
          </Form.Item>
          <Form.Item label="模型 ID" required>
            <div className="flex items-start gap-2">
              <Form.Item name="model" noStyle rules={[{ required: true, whitespace: true, message: '请选择或输入模型 ID' }]}>
                <AutoComplete className="flex-1 min-w-0" options={options} placeholder={providerId === 'ollama' ? '例如 qwen3:4b，须已在本地下载' : '选择或输入完整模型 ID'} filterOption={(input, option) => String(option?.value).toLowerCase().includes(input.toLowerCase())} />
              </Form.Item>
              <Button loading={busy === 'discover'} disabled={!!busy && busy !== 'discover'} onClick={discover} icon={<ReloadOutlined />}>获取列表</Button>
            </div>
            <p className="text-xs text-surface-muted mt-2">预置 ID 仅供填写参考，以账户实际可用模型为准。支持手动输入。</p>
          </Form.Item>
          <Form.Item name="is_default" label="设为默认模型" valuePropName="checked"><Switch /></Form.Item>
          {feedback && <Alert type={feedback.type} message={feedback.text} showIcon className="mb-4" />}
        </Form>
      </Modal>
    </div>
  )
}
