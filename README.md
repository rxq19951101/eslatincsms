<!--
本文件用于说明项目启动步骤与预期行为，涵盖 csms、charger-sim、admin、app 模块。
不包含任何机密或外部链接，所有服务均基于本地端口运行。
-->

## 本地 OCPP 1.6J 测试平台 (Chinese/English)

### 模块概览
- **csms (9000)**: FastAPI 实现的 OCPP 1.6J 本地测试服务器。提供 WebSocket `/ocpp`（接收简化版 OCPP 动作）与 REST：`/health`、`/chargers`、`/api/updateLocation`、`/api/messages`（消息管理）。
- **charger-sim**: Python 简易“充电桩”模拟器，支持设置充电桩位置（`--lat`、`--lng`、`--address`），通过 WebSocket 发送 OCPP 消息。
- **admin (3000)**: Next.js 14 (App Router)。多页面管理：首页、地图视图、监测中心、客服消息（查看/回复用户消息）。
- **app**: Expo React Native 移动应用。底部标签导航：Support（发送消息） / Map（地图） / Scan（扫码） / History / Account。

### 端口
- csms: `9000`
- admin: `3000`
- db (PostgreSQL): `5432`
- redis: `6379`

### 前置要求

#### 必需
- **Docker** 20.10+ 与 **Docker Compose** v2.0+
  - macOS: [Docker Desktop](https://www.docker.com/products/docker-desktop/)
  - Linux: `sudo apt install docker.io docker-compose-plugin` 或使用官方安装脚本
  - Windows: [Docker Desktop](https://www.docker.com/products/docker-desktop/)
  - 安装后验证: `docker --version` 与 `docker compose version`

#### 可选（本地开发）
- Python 3.10+ (用于本地运行 charger-sim，或使用 Docker 无需安装)
- Node.js 18+ (用于本地运行 admin 或 app)

### 启动步骤
1) 验证 Docker 安装
```bash
docker --version
docker compose version
```

2) 构建与启动容器
```bash
docker compose up --build
```

3) 访问管理界面
- 浏览器打开 `http://localhost:3000/chargers`

4) 运行额外模拟器（可选，多实例）
```bash
# 新开终端运行本地 Python 模拟器（需本机已安装 Python 3.10+）
cd charger-sim
pip3 install -r requirements.txt

# 【推荐】交互式控制：手动切换充电桩状态
python3 interactive.py --id MY-CHARGER-1

# 设置充电桩位置（经纬度）
python3 interactive.py --id CP-BEIJING-1 --lat 39.9042 --lng 116.4074 --address "北京市朝阳区"

# 自动完整流程：单实例（默认 CP-0001）
python3 simulator.py

# 自定义 ID
python3 simulator.py --id MY-CHARGER-1

# 并发启动 N 个实例（CP-0001 到 CP-00NN）
python3 simulator.py --count 5

# 自定义 ID 前缀 + 并发数量
python3 simulator.py --id EV-0001 --count 3  # EV-0001, EV-0002, EV-0003

# 或使用容器方式再起一个模拟器（无需本地 Python）
docker compose run --rm charger-sim python simulator.py --id SIM-LOCAL-2 --url ws://csms:9000/ocpp
docker compose run --rm charger-sim python simulator.py --count 3 --url ws://csms:9000/ocpp
```

5) 运行移动端 app（可选）
```bash
# 新开终端
cd app
npm install
npm start

# 在终端选择运行平台：
# - 按 w 在浏览器中打开（推荐新手）
# - 按 i 在 iOS 模拟器运行（macOS only）
# - 按 a 在 Android 模拟器运行
# - 扫码在真机运行（需安装 Expo Go）
```

**重要**：如果 App 出现网络错误（Network request failed）：
- **Android 和 iOS 真机**：已自动配置为使用电脑 IP `192.168.20.34`
- **Web 浏览器**：已自动配置为 `http://localhost:9000`
- 如果您的电脑 IP 不同，请修改 `app/config.ts` 第 11 行：
  - macOS/Linux：运行 `ifconfig` 查找本机 IP
  - Windows：运行 `ipconfig` 查找本机 IP
  - 修改 `const COMPUTER_IP = 'YOUR_IP';`

**修改配置后必须重启 App**：
1. 在 Expo 终端按 `r` 重新加载，或
2. 停止并重新运行 `npm start`

配置示例：
```typescript
const COMPUTER_IP = '192.168.1.100'; // 改为您的电脑 IP
```

### 期望日志/访问 URL

#### 启动成功标志
执行 `docker compose up --build` 后，所有服务启动正常时应看到：

```
✅ redis    | Redis 启动
✅ db       | PostgreSQL 启动
✅ csms     | Uvicorn running on http://0.0.0.0:9000
✅ admin    | ready - started server on 0.0.0.0:3000
✅ charger-sim | [CP-DOCKER-1] ✓ connected
```

#### 访问 URL
- **Admin 管理界面**:
  - 首页：`http://localhost:3000`
  - 地图视图：`http://localhost:3000/map`
  - 监测中心：`http://localhost:3000/chargers`
  - 客服消息：`http://localhost:3000/messages`
- **CSMS API**:
  - Health: `http://localhost:9000/health`
  - 充电桩列表：`http://localhost:9000/chargers`
  - 更新位置：`POST http://localhost:9000/api/updateLocation`
  - 消息列表：`GET http://localhost:9000/api/messages`
  - 发送消息：`POST http://localhost:9000/api/messages`
  - 回复消息：`POST http://localhost:9000/api/messages/reply`
- **PostgreSQL**: `localhost:5432` (user: local, password: local, db: ocpp)
- **Redis**: `localhost:6379`

#### 日志输出示例

**csms 日志**:
```
INFO:     Uvicorn running on http://0.0.0.0:9000
INFO:     Application startup complete
INFO: [CP-DOCKER-1] WebSocket connected, subprotocol=ocpp1.6
INFO: [CP-DOCKER-1] New charger registered
INFO: [CP-DOCKER-1] <- OCPP Heartbeat | payload={}
INFO: [CP-DOCKER-1] -> OCPP HeartbeatResponse | currentTime=2025-10-30T23:45:00.123456+00:00
INFO: [CP-DOCKER-1] <- OCPP StartTransaction | payload={"transactionId": 1001}
INFO: [CP-DOCKER-1] -> OCPP StartTransactionResponse | txId=1001
INFO: [CP-DOCKER-1] <- OCPP MeterValues | payload={"meter": 50}
INFO: [CP-DOCKER-1] -> OCPP MeterValuesAccepted | meter=50
```

**admin 日志**:
```
✓ Ready in 2.1s
○ Compiling /chargers ...
○ Compiled /chargers in 123ms
```

**charger-sim 日志**:
```
[CP-DOCKER-1] connecting: ws://csms:9000/ocpp?id=CP-DOCKER-1
[CP-DOCKER-1] ✓ connected
[CP-DOCKER-1] → BootNotification {"vendor": "SIM", "model": "SIM-1"}
[CP-DOCKER-1] ← BootNotification status=Accepted
[CP-DOCKER-1] → Heartbeat
[CP-DOCKER-1] ← Heartbeat status=N/A
...
[CP-DOCKER-1] ✓ sequence completed
```

**admin 页面显示**:
- 监测中心（/chargers）：大屏展示所有充电桩（在线+历史记录）
  - 实时离线监测：超过 30 秒未更新标记为红色“离线”
  - 时间显示：精确到秒 + 相对时间（如：3s ago）
  - 离线桩：红色背景高亮 + 离线状态标识
  - 自动刷新：每 3 秒轮询最新状态
- 地图视图（/map）：显示充电桩位置和状态
  - 标记点颜色：绿色可用、橙色充电中、红色故障/离线
  - 点击标记点显示详细信息
  - 自动刷新：每 3 秒更新位置和状态

#### 离线监测演示
```
1. 启动交互式模拟器
   python3 interactive.py --id TEST-001

2. 发送 boot 命令，admin 页面显示"在线"

3. Ctrl+C 断开连接

4. 等待 30 秒后，admin 页面该桩变为：
   - 红色背景高亮
   - 状态标记"离线"
   - 显示最后在线时间 + 已离线时长
```

#### 二维码测试演示
```
1. 启动充电桩模拟器
   docker compose up

2. 访问 Admin 界面
   http://localhost:3000/chargers

3. 每个充电桩卡片左侧显示二维码

4. 启动 App（在 app 目录）
   npm start
   按 w 在浏览器中打开，或按 i/a 在模拟器中打开

5. 在 App 的 Scan 页面
   - 使用相机扫描 Admin 界面上的二维码
   - 或者扫描终端中打印的 ASCII 二维码

6. 扫码成功后跳转到 Session 页面
   - 显示充电桩 ID、状态、电量等信息
```

#### 交互式控制示例
使用 `python3 interactive.py` 进行手动控制充电桩状态：
```
[MY-CHARGER-1] > boot
[MY-CHARGER-1] → BootNotification
[MY-CHARGER-1] ← BootNotification status=Accepted

[MY-CHARGER-1] > status Available
[MY-CHARGER-1] → StatusNotification {"status": "Available"}

[MY-CHARGER-1] > auth TAG-123
[MY-CHARGER-1] → Authorize {"idTag": "TAG-123"}

[MY-CHARGER-1] > start 1001
[MY-CHARGER-1] → StartTransaction {"transactionId": 1001}

[MY-CHARGER-1] > meter 50
[MY-CHARGER-1] → MeterValues {"meter": 50}

[MY-CHARGER-1] > stop
[MY-CHARGER-1] → StopTransaction {"reason": "Local"}

[MY-CHARGER-1] > quit
```

### 目录结构（节选）
```
csms/
  Dockerfile
  requirements.txt
  app/main.py
charger-sim/
  Dockerfile
  requirements.txt
  simulator.py
  interactive.py
admin/
  Dockerfile
  package.json
  next.config.js
  app/chargers/page.tsx
  app/layout.tsx
  app/page.tsx
  tsconfig.json
app/
  package.json
  app.json
  README.md
  App.tsx
  screens/
    HomeScreen.tsx
    ScanScreen.tsx
    SessionScreen.tsx
  tsconfig.json
  babel.config.js
docker-compose.yml
.env.example
```

### app 本地启动（可选）

app 为 Expo React Native 应用，需在本地运行。

#### 前置准备
```bash
# 确保已安装 Node.js 18+ 和 npm
node --version
npm --version

# 安装 Expo CLI（可选，npm start 会自动使用）
npm install -g @expo/cli
```

#### 启动步骤
```bash
cd app

# 安装依赖（如遇到依赖冲突，请使用 --legacy-peer-deps）
npm install --legacy-peer-deps

# 启动开发服务器
npm start
```

#### 运行平台选择
启动后在终端选择运行平台：

| 按键 | 平台 | 说明 |
|------|------|------|
| `i` | iOS 模拟器 | 需要安装 Xcode（macOS only） |
| `a` | Android 模拟器 | 需要安装 Android Studio |
| `w` | Web 浏览器 | 所有平台可用（推荐新手） |
| 二维码 | 真机调试 | 安装 Expo Go 后扫码 |

#### 访问地址
启动后 Expo 会自动打开或显示：
- **开发服务器**: `http://localhost:8081`（Expo DevTools）
- **Web 版本**: 按 `w` 后在浏览器打开

#### 功能说明
- **Home 页面**: 输入/选择充电桩 ID → 跳转 Session
- **Scan 页面**: 使用 `expo-camera` 实现真实扫码功能
- **Session 页面**: 展示充电桩状态（ID、状态、会话信息）
- **二维码功能**: 
  - 充电桩模拟器启动时会在控制台打印二维码
  - Admin 界面每个充电桩卡片都会显示二维码
  - 使用 App 扫描二维码即可快速连接充电桩

详细说明见 `app/README.md`。

### 故障排除

#### 数据库连接错误
如遇到 `FATAL: database "local" does not exist`:
```bash
# 停止并清理容器
docker compose down -v

# 重新启动（这将重新创建数据卷）
docker compose up --build
```

#### 端口占用
如端口被占用，可临时修改 `docker-compose.yml` 中的端口映射：
```yaml
ports:
  - "19000:9000"  # 而不是 9000:9000
```

#### Docker 服务管理
```bash
# 启动所有服务
docker compose up

# 后台启动
docker compose up -d

# 停止所有服务
docker compose stop

# 停止并删除容器
docker compose down

# 停止并删除容器+数据卷
docker compose down -v

# 重启所有服务
docker compose restart

# 重启特定服务
docker compose restart csms

# 重新构建并启动
docker compose up --build

# 查看运行状态
docker compose ps
```

#### 充电桩模拟器控制
```bash
# 终止本地 Python 模拟器
# 按 Ctrl+C 或 Cmd+C

# 终止 Docker 容器中的模拟器
docker compose stop charger-sim

# 重启 Docker 模拟器
docker compose restart charger-sim

# 删除 Docker 模拟器容器
docker compose rm -f charger-sim

# 查看模拟器日志
docker compose logs -f charger-sim
```

#### 查看 OCPP 协议日志
```bash
# 查看 csms 的 OCPP 协议日志（推荐）
docker compose logs -f csms | grep "OCPP"

# 查看所有服务日志
docker compose logs -f

# 查看特定服务日志
docker compose logs -f csms      # CSMS OCPP 消息日志
docker compose logs -f admin     # Next.js 访问日志
docker logs -f db                # PostgreSQL 日志
docker logs -f redis             # Redis 日志

# 仅查看 csms 心跳消息
docker compose logs -f csms | grep "Heartbeat"
```

#### npm command not found
macOS/Linux 上需要先安装 Node.js 和 npm:
```bash
# macOS - 使用 Homebrew 安装（推荐）
brew install node

# macOS - 或使用官方安装包
# 访问 https://nodejs.org 下载 LTS 版本

# Linux (Ubuntu/Debian)
sudo apt update
sudo apt install nodejs npm

# 验证安装
node --version  # 应显示 v18+
npm --version   # 应显示 9+

# 如果已安装但 npm 不可用，尝试重新安装
brew reinstall node
```

#### npm install 依赖冲突
如遇到 `ERESOLVE unable to resolve dependency tree` 错误：
```bash
# 方法 1：使用 --legacy-peer-deps 标志（推荐）
cd app
npm install --legacy-peer-deps

# 方法 2：使用 --force 标志
npm install --force

# 原因：react-native 0.74.3 要求 react 18.2.0，但其他依赖可能要求 18.3.1
# 已在 package.json 中固定为 react@18.2.0 以确保兼容性
```

#### pip command not found
macOS/Linux 上通常使用 `pip3` 和 `python3`:
```bash
# macOS/Linux
pip3 install -r requirements.txt
python3 simulator.py

# 如果只有 python 可用
python -m pip install -r requirements.txt

# 或使用 Docker 容器（无需本地 Python）
docker compose run --rm charger-sim python simulator.py
```

#### Python 版本不兼容
如遇到 `unsupported operand type(s) for |` 等类型错误：
- 升级到 Python 3.10+: `brew install python@3.11` (macOS)
- 或使用 Docker 容器（已修复兼容性问题）

#### 设置充电桩位置
充电桩模拟器支持设置经纬度位置：
```bash
python3 interactive.py --id CP-001 --lat 39.9042 --lng 116.4074 --address "北京市朝阳区"

# 参数说明：
# --id: 充电桩ID
# --lat: 纬度（必填）
# --lng: 经度（必填）
# --address: 地址（可选）
```

设置后充电桩位置会自动保存到 CSMS，可在 Admin 地图视图和 App 地图页面查看。

#### 交互式控制器命令速查
使用 `python3 interactive.py` 后可用命令：
```bash
boot                    # 发送 BootNotification
hb                      # 发送 Heartbeat  
status Available        # 发送状态：Available/Preparing/Charging/Faulted 等
auth TAG-123           # 发送 Authorize（授权用户）
start 1001             # 开始充电（可选指定交易ID）
meter 50               # 上报电量（单位：Wh）
stop                   # 停止充电
quit                   # 退出交互模式
```

### 说明与限制
- WebSocket `/ocpp` 为本地测试用，使用简化 JSON schema（字段 `action` 指明动作；并非完整 OCPP 帧编码）。
- 状态存储默认写入 Redis（容器内服务 `redis`），键空间简单直观，便于观察。
- 充电桩位置通过 `POST /api/updateLocation` 设置，支持 latitude、longitude、address 字段。
- 本仓库用于本地演示与扩展起步，未实现完整鉴权与生产加固。

---

## 📚 项目文档

所有详细文档已整理到 `docs/` 文件夹，按分类组织：

- **📦 部署文档** - [docs/deployment/](docs/deployment/)
  - [生产环境部署指南](docs/deployment/PRODUCTION_DEPLOYMENT.md)
  - [分布式部署指南](docs/deployment/DISTRIBUTED_DEPLOYMENT.md)
  - [快速开始：分布式部署](docs/deployment/QUICK_START_DISTRIBUTED.md)

- **🧪 验证文档** - [docs/validation/](docs/validation/)
  - [OCPP验证工具说明](docs/validation/OCPP_VALIDATION_README.md)

- **🏗️ 架构文档** - [docs/architecture/](docs/architecture/)
  - [项目结构说明](docs/architecture/PROJECT_STRUCTURE.md)
  - [重构总结](docs/architecture/REFACTORING_SUMMARY.md)

- **💻 开发文档** - [docs/development/](docs/development/)
  - [OCPP功能完成清单](docs/development/OCPP_FEATURES_COMPLETE.md)

**完整文档索引** → [docs/DOCUMENTATION_INDEX.md](docs/DOCUMENTATION_INDEX.md)

