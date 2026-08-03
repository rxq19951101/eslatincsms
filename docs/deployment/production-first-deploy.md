# 生产服务器首次部署

## 1. DNS 与防火墙

部署前完成以下配置：

- `admin.eslatin.com.co` 的 A 记录指向服务器公网 IPv4 地址。
- `api.eslatin.com.co` 的 A 记录指向服务器公网 IPv4 地址。
- 云安全组仅开放：管理来源 IP 到 22/TCP、互联网到 80/TCP、443/TCP、443/UDP。
- 不开放 3000、9000、5432、6379。
- 当前 Compose 公网绑定以 IPv4 为基线，不要配置不可达的 AAAA 记录。
- 出站允许 DNS、HTTP/HTTPS、系统时间同步以及所配置 SMTP 服务的端口。

## 2. 创建生产环境文件

```bash
cp .env.production.example .env.production
chmod 600 .env.production
```

至少替换所有 `CHANGE_ME`、`example.com`，并保证以下关系成立：

```text
CORS_ALLOW_ORIGINS=https://admin.eslatin.com.co
PUBLIC_API_BASE_URL=https://api.eslatin.com.co
NEXT_PUBLIC_CSMS_HTTP=https://api.eslatin.com.co
NEXT_PUBLIC_API_BASE_URL=https://api.eslatin.com.co
ACME_EMAIL=support@eslatin.com.co
```

数据库、Redis 密码如果包含 URL 保留字符，`DATABASE_URL` 和 `REDIS_URL` 中必须使用 URL 编码后的密码。

## 3. 首次启动

```bash
./scripts/validate_prod_env.sh --first-boot

docker compose \
  --env-file .env.production \
  -f docker-compose.prod.yml \
  up -d --build
```

Caddy 会在域名解析和 80/443 入站正常后自动申请 TLS 证书。查看状态：

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml ps
docker compose --env-file .env.production -f docker-compose.prod.yml logs --tail 100 proxy
```

## 4. 外部验收

```bash
curl --fail --silent --show-error https://api.eslatin.com.co/livez
curl --fail --silent --show-error https://api.eslatin.com.co/readyz
curl --head https://admin.eslatin.com.co/login
curl --head http://admin.eslatin.com.co/login
```

最后一条应返回到 HTTPS 的重定向。充电桩连接地址使用：

```text
wss://api.eslatin.com.co/ocpp/<充电桩身份标识>
```

不得使用 `ws://`、服务器 IP、3000 或 9000 作为生产公网地址。

## 5. 首启后收口

确认两个管理员均可登录后，清空 `.env.production` 中：

```text
CSMS_BOOTSTRAP_SUPER_ADMIN_PASSWORD=
CSMS_BOOTSTRAP_TENANT_ADMIN_PASSWORD=
```

然后执行：

```bash
./scripts/validate_prod_env.sh
docker compose --env-file .env.production -f docker-compose.prod.yml up -d
```

不要删除 `caddy_data`、`caddy_config`、`postgres_data`、`redis_data` 或 `qr_data` 数据卷。
