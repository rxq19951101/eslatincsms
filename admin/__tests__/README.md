# Admin 单元测试

## 测试结构

```
__tests__/
├── utils/
│   └── api.test.ts          # API工具函数测试
├── components/
│   └── ChargerCard.test.tsx # 组件测试
└── pages/
    └── chargers.test.tsx    # 页面测试
```

## 运行测试

### 方法1: 运行所有测试

```bash
cd admin
npm test
```

### 方法2: 监听模式（开发时推荐）

```bash
cd admin
npm run test:watch
```

### 方法3: 生成覆盖率报告

```bash
cd admin
npm run test:coverage
```

### 方法4: 运行特定测试文件

```bash
cd admin
npm test -- api.test.ts
```

## 测试覆盖范围

### 工具函数测试
- ✅ `getApiBase()`: API基础URL获取
  - 环境变量优先级
  - 浏览器环境自动检测
  - 服务端渲染默认值

### 组件测试
- ✅ ChargerCard: 充电桩卡片组件
  - 数据渲染
  - 缺失数据处理

### 页面测试
- ✅ Chargers页面
  - 数据加载
  - 错误处理
  - 筛选功能

## 注意事项

1. 使用Jest作为测试框架
2. 使用React Testing Library进行组件测试
3. Mock了Next.js router和window对象
4. 测试环境使用jsdom模拟浏览器环境

