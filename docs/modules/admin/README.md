# Admin - 充电桩管理后台

Next.js 14 构建的充电桩运营管理平台。

## 功能特性

- ✅ 充电桩监测中心（实时状态大屏）
- ✅ 地图视图（Leaflet 地图）
- ✅ 充电桩管理（检测、录入、配置）
- ✅ 客服消息（查看和回复用户消息）
- ✅ 实时数据刷新（每 3 秒）

## 快速开始

### 开发模式

```bash
cd admin
npm install
npm run dev
```

访问 http://localhost:3000

### 生产构建

```bash
npm run build
npm start
```

## 环境变量

```bash
NEXT_PUBLIC_CSMS_HTTP=http://localhost:9000
```

## 依赖

- Next.js 14
- React 18
- TypeScript
- Leaflet (地图)
- SWR (数据获取)

## 许可证

[您的许可证]
