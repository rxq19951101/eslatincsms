#
# 本文件用于构建 admin (Next.js 14) 镜像：开发模式运行在 3000 端口。
# 应用使用 App Router，并轮询 csms /chargers。

FROM node:20-alpine

WORKDIR /app

COPY package*.json ./
COPY tsconfig.json next.config.js next-env.d.ts ./
COPY app ./app

RUN npm install --no-audit --no-fund

ENV PORT=3000
EXPOSE 3000

CMD ["npm", "run", "dev"]


