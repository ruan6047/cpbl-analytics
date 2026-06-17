# syntax=docker/dockerfile:1
FROM node:22-alpine AS builder
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# NEXT_PUBLIC_* 於 build 時內嵌進前端 JS，必須在 build 前設定（runtime env 無效）。
# 預設空字串＝瀏覽器走同源相對路徑（prod 由 nginx 將 /api 轉給 cpbl-api）；
# 需要絕對網址時以 --build-arg NEXT_PUBLIC_API_URL=... 覆蓋。
ARG NEXT_PUBLIC_API_URL=""
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
# 資料頁為 force-dynamic，build 時不會預抓 API
RUN npm run build

FROM node:22-alpine
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000
RUN addgroup -S app && adduser -S app -G app
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
USER app
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s \
    CMD wget -qO- http://localhost:3000/ || exit 1
CMD ["node", "server.js"]
