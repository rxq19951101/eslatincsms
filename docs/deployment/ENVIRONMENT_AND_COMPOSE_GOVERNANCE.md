# 环境与 Compose 选择规范

状态：ACTIVE

本文是项目环境和 Compose 入口的唯一选择规范。它与根目录 `AGENTS.md` 的“环境与 Compose 硬性治理”一起生效。

## 1. 唯一环境矩阵

| 目标 | 唯一 Compose 入口 | 环境标识 | 端口/用途 | 允许的环境配置来源 |
|---|---|---|---|---|
| 本地默认开发栈 | `docker-compose.yml` | `development` | 默认本地端口；兼容旧的无 `-f` 命令 | 根目录 `.env`，必要时使用已存在的 `admin/.env.local` 构建参数 |
| 隔离开发栈 | `docker-compose.dev.yml` | `development` | CSMS 8000、Admin 3001、DB 5433、Redis 6380、MQTT 1884/9002 | 根目录 `.env` 或命令显式注入的既有开发变量 |
| 本地测试栈 | `docker-compose.test.yml` | `test` | CSMS 8001、Admin 3002、DB 5434、Redis 6381、MQTT 1885/9003 | `.env.test.local`（仅本地、仅忽略文件）或已批准的 CI secret 注入 |
| 生产栈 | `docker-compose.prod.yml` | `production` | 仅生产服务器；域名/TLS/反向代理 | `.env.production` 或生产 secret provider |
| 仅 CSMS 特殊调试 | `docker-compose.csms-only.yml` | 由文件内配置决定 | 无 Admin、无 charger-sim；只用于明确批准的 CSMS 调试 | 既有开发/测试注入方式；不得作为完整环境替代 |
| 旧命令兼容入口 | `docker-compose.local-prod.yml` | 继承 `docker-compose.yml` | 不得引入独立配置或数据卷 | 与 `docker-compose.yml` 完全一致 |

不得创建或使用未登记的第七个入口。`docker-compose.local-prod.yml` 是兼容包装器，不是独立环境。

## 2. 标准选择规则

### 本地开发

```bash
docker compose -f docker-compose.yml up -d --build
```

需要隔离开发端口时才使用：

```bash
docker compose -f docker-compose.dev.yml up -d --build
```

### 本地测试

测试必须显式选择测试 Compose，并使用同一份测试环境注入：

```bash
docker compose --env-file .env.test.local -f docker-compose.test.yml config --quiet
docker compose --env-file .env.test.local -f docker-compose.test.yml up -d --build
```

如果当前 `docker-compose.test.yml` 尚未映射某个变量，必须修改已登记的测试 Compose 并经过配置审查；不得另建 `docker-compose.test-xxx.yml` 或临时 env 文件绕过。

### 生产

生产只能由明确的生产发布流程选择：

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml config --quiet
docker compose --env-file .env.production -f docker-compose.prod.yml up -d --build
```

当前项目治理仍禁止 Agent 自行部署生产或打开真实支付。

## 3. 配置文件规则

- `.env.example`、`csms/.env.example`、`app/.env.example` 和 `.env.production.example` 是模板，不是运行时密钥文件。
- `.env.test.local` 是本地测试私密配置的唯一批准文件；它必须保持 Git ignored，不得复制出 `.env.test.local.bak`、`.env.test.local.2`、`.env.sandbox` 等变体。
- `.env.production` 只能用于生产发布流程；测试 token 不得因方便而写入生产文件或生产 Compose 默认值。
- Access Token、Webhook Secret、密码和完整支付卡数据只能注入后端或本地测试服务，绝不能进入 App/Admin 前端构建参数。
- 变量名变更必须同时更新读取代码、模板、对应 Compose 映射、测试和文档；不能只改一处。

## 4. 一致性门禁

启动或测试前必须核对：

1. `ENVIRONMENT` 在前端、后端、模拟器和 QA 目标中一致；
2. Compose 文件、env 文件、API 地址、WebSocket 地址、Webhook 地址和 Provider 模式属于同一环境；
3. 数据库、Redis、MQTT 的端口、网络和数据卷没有跨环境复用；
4. 测试数据来自同一份批准基线，不通过手工插入或临时文件掩盖环境不一致；
5. 支付开关、密钥和 Webhook 验证配置与目标环境匹配。

任何一项无法证明时，QA/Agent 必须返回：

```text
BLOCKED: environment-mismatch
REQUIRED_HUMAN_DECISION: 是否批准修改既有环境/Compose/配置选择
EVIDENCE_REQUIRED: <具体缺失证据>
```

不得继续下游架构批准、实现或 E2E 结论。

## 5. 变更申请模板

需要新增环境文件、Compose 入口或修改环境映射时，必须先创建 change draft，并包含：

```text
ENVIRONMENT / COMPOSE CHANGE REQUEST
Change ID:
Requester:
Target environment:
Current approved files:
Requested files or mappings:
Why existing entry cannot be reused:
Variables and secrets affected:
Frontend/backend/simulator consistency impact:
Ports/volumes/networks impact:
Validation commands:
Rollback plan:
Human decision required: YES
Status: awaiting-user-approval
```

在用户明确批准前，只能分析和提出方案，不得创建文件、修改配置或启动替代栈。
