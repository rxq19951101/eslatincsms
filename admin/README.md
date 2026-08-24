# 充电桩运营平台 - 后台管理系统

基于 Next.js 14 + Tailwind CSS + shadcn/ui 构建的现代化暗色主题 SaaS Dashboard。

## 技术栈

- **框架**: Next.js 14 (App Router)
- **样式**: Tailwind CSS
- **UI组件**: shadcn/ui
- **状态管理**: Zustand
- **数据获取**: SWR
- **表单处理**: React Hook Form + Zod
- **图表**: Recharts
- **地图**: Leaflet
- **图标**: Lucide React

## 功能特性

- ✅ 暗色主题 SaaS Dashboard 风格
- ✅ 完整的认证系统（登录、Token 管理、自动刷新）
- ✅ 多租户支持
- ✅ Dashboard 概览（KPI 卡片、趋势图表）
- ✅ 充电桩管理（列表、详情、远程控制）
- ✅ 交易管理
- ✅ 统计报表
- ✅ 告警管理
- ✅ 用户管理
- ✅ 地图视图
- ✅ 系统设置

## 开发

```bash
# 安装依赖
npm install

# 开发模式（端口 3000）
npm run dev

# 构建
npm run build

# 启动生产服务器
npm start
```

## 环境变量

复制 `.env.example` 到 `.env.local` 并配置：

```env
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

## 项目结构

```
admin/
├── app/                    # Next.js App Router
│   ├── (auth)/            # 认证相关路由
│   └── (dashboard)/       # 后台管理路由
├── components/
│   ├── ui/                # shadcn/ui 基础组件
│   ├── layout/            # 布局组件
│   ├── shared/            # 通用业务组件
│   └── map/               # 地图组件
├── features/              # 业务模块组件
├── lib/                   # 工具函数和 API 客户端
├── hooks/                 # React Hooks
├── store/                 # Zustand 状态管理
└── types/                 # TypeScript 类型定义
```

## API 集成

所有 API 请求通过 `lib/api.ts` 统一处理，自动包含：
- Token 认证
- 多租户支持
- 401 自动刷新
- 错误处理

## 设计风格

- 暗色主题（深灰蓝色背景）
- 半透明卡片（带圆角、柔光阴影）
- 紫蓝渐变强调色
- 响应式设计

## License

Private