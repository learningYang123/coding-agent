import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { ConfigProvider, App as AntdApp, theme } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import 'antd/dist/reset.css'
import 'highlight.js/styles/github-dark.css'

import App from './App'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ConfigProvider
      locale={zhCN}
      theme={{
        algorithm: theme.darkAlgorithm,
        token: {
          colorPrimary: '#5b9bff',
          colorBgBase: '#23324a',
          colorBgLayout: '#213149',
          colorBgContainer: '#2d3e58',
          colorBgElevated: '#354864',
          colorTextBase: '#edf3fc',
          colorText: '#edf3fc',
          colorTextSecondary: '#b6c4d8',
          colorTextPlaceholder: '#9eafc8',
          colorLink: '#8ec1ff',
          colorBorder: '#495b75',
          borderRadius: 8,
        },
        components: {
          Layout: { headerBg: '#2d3e58', siderBg: '#2d3e58', bodyBg: '#213149' },
        },
      }}
    >
      <AntdApp>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </AntdApp>
    </ConfigProvider>
  </React.StrictMode>,
)
