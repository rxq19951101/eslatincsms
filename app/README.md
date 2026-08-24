# EsLatin 充电桩移动应用

基于 React Native + Expo 开发的电动车充电桩查找和预订应用。

## 技术栈

- **框架**: React Native + Expo SDK 54
- **语言**: TypeScript
- **导航**: React Navigation 6.x
- **状态管理**: Redux Toolkit + RTK Query
- **HTTP客户端**: Axios
- **本地存储**: AsyncStorage
- **UI组件**: React Native Paper
- **地图**: MapLibre GL Native + OpenStreetMap

## 项目结构

```
app/
├── src/
│   ├── api/              # API接口
│   │   ├── client.ts     # Axios配置和拦截器
│   │   └── auth.ts       # 认证API
│   ├── screens/          # 页面组件
│   │   ├── auth/         # 认证相关页面
│   │   │   ├── WelcomeScreen.tsx              # 欢迎页
│   │   │   ├── EmailLoginScreen.tsx           # 邮箱登录
│   │   │   ├── EmailRegisterScreen.tsx        # 邮箱注册
│   │   │   ├── EmailVerificationScreen.tsx    # 邮箱验证等待
│   │   │   ├── VerificationSuccessScreen.tsx  # 验证成功
│   │   │   ├── ForgotPasswordScreen.tsx       # 忘记密码
│   │   │   └── ResetPasswordScreen.tsx        # 重置密码
│   │   ├── home/         # 首页相关
│   │   ├── booking/      # 预订相关
│   │   ├── wallet/       # 钱包相关
│   │   └── account/      # 账户相关
│   ├── components/       # 可复用组件
│   │   ├── common/       # 通用组件
│   │   ├── map/          # 地图组件
│   │   ├── station/      # 充电站组件
│   │   └── auth/         # 认证组件
│   ├── navigation/       # 导航配置
│   │   └── RootNavigator.tsx
│   ├── store/            # Redux状态管理
│   │   ├── index.ts      # Store配置
│   │   ├── slices/       # Redux Slices
│   │   │   └── authSlice.ts
│   │   └── services/     # RTK Query服务
│   ├── hooks/            # 自定义Hooks
│   │   └── useRedux.ts
│   ├── utils/            # 工具函数
│   │   └── tokenManager.ts
│   ├── constants/        # 常量配置
│   │   └── config.ts
│   ├── types/            # TypeScript类型定义
│   │   └── index.ts
│   └── assets/           # 静态资源
├── App.tsx              # 应用入口
├── package.json
└── tsconfig.json
```

## 已完成功能

### Phase 1: 认证流程 ✅

#### 1.1 项目初始化 ✅
- Expo项目创建
- TypeScript配置
- 目录结构搭建
- 依赖包安装

#### 1.2 Token管理 ✅
- Token存储/获取/清除
- JWT解析
- Token过期检测
- 自动刷新Token机制

#### 1.3 欢迎页面 ✅
- Logo展示
- 邮箱登录按钮
- 社交登录按钮组（Google/Apple/Facebook）

#### 1.4 邮箱登录页面 ✅
- 邮箱输入
- 密码输入（显示/隐藏）
- 记住我选项
- 忘记密码链接
- 表单验证

#### 1.5 邮箱注册页面 ✅
- 全名输入
- 邮箱输入
- 密码输入（带强度指示器）
- 确认密码
- 同意条款
- 表单验证

#### 1.6 邮箱验证等待页面 ✅
- 验证邮件发送提示
- 重发邮件功能（带倒计时）
- 更改邮箱
- 返回登录

#### 1.7 验证成功页面 ✅
- 成功动画
- 自动跳转主页

#### 1.8 忘记密码页面 ✅
- 邮箱输入
- 发送重置链接
- 发送成功提示

#### 1.9 重置密码页面 ✅
- 新密码输入（带强度指示器）
- 确认密码
- Deep Link参数处理
- 表单验证

### API配置

- **Axios客户端配置**: 自动Token注入、刷新机制
- **请求拦截器**: Token过期检测和刷新
- **响应拦截器**: 401错误处理
- **错误处理**: 统一的错误处理函数

### Redux状态管理

- **Auth Slice**: 用户认证状态、登录/注册/登出actions
- **异步Thunks**: 邮箱登录、注册、社交登录
- **Error处理**: 统一的错误状态管理

## 运行项目

### 安装依赖

```bash
cd app
npm install
```

### 启动开发服务器

```bash
npm start
```

### 运行iOS

```bash
npm run ios
```

### 运行Android

```bash
npm run android
```

### 运行Web

```bash
npm run web
```

## 环境配置

在项目根目录创建 `.env` 文件：

```env
EXPO_PUBLIC_API_URL=http://localhost:9000
EXPO_PUBLIC_TENANT_ID=your-tenant-id
```

## API端点

### 认证API（基于计划）

- `POST /api/v1/app/auth/register-email` - 邮箱注册
- `POST /api/v1/app/auth/login-email` - 邮箱登录
- `GET /api/v1/app/auth/verify-email` - 验证邮箱
- `POST /api/v1/app/auth/resend-verification` - 重发验证邮件
- `POST /api/v1/app/auth/reset-password` - 发送重置密码邮件
- `POST /api/v1/app/auth/confirm-reset-password` - 确认重置密码
- `POST /api/v1/app/auth/social/{provider}` - 社交登录
- `POST /api/v1/app/auth/refresh` - 刷新Token
- `POST /api/v1/app/auth/logout` - 登出
- `GET /api/v1/app/auth/me` - 获取当前用户信息

## 待完成功能

### Phase 1.10: 社交登录集成
- Google登录SDK集成
- Apple登录集成
- Facebook登录集成

### Phase 2: 主页和地图
- 位置授权页面
- 充电站列表
- 地图视图（MapLibre + OpenStreetMap）
- 充电站详情

### Phase 3: 预订和充电
- 我的预订页面
- 预订详情
- 取消预订
- 充电过程实时显示
- 充电完成页面

### Phase 4: 钱包
- 钱包余额
- 充值功能
- 交易历史

### Phase 5: 账户
- 账户信息
- 支付方式管理

### Phase 6: 优化和测试
- UI优化
- 性能优化
- 单元测试
- E2E测试

## 注意事项

1. **后端API**: 需要后端实现邮箱验证和密码重置功能
2. **邮件服务**: 需要配置邮件服务（SendGrid/Mailgun/AWS SES）
3. **Deep Linking**: 需要配置应用的URL Scheme和Universal Links
4. **社交登录**: 需要在各平台注册应用并获取API密钥
5. **地图API**: 需要配置MapLibre和OpenStreetMap

## 开发规范

- 使用TypeScript进行类型检查
- 遵循ESLint代码规范
- 组件采用函数式编程
- 使用Redux Toolkit管理全局状态
- API调用统一使用async/await
- 错误处理使用try/catch
- 所有API响应进行类型定义

## License

MIT
