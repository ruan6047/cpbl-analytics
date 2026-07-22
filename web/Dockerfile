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
# HOSTNAME=0.0.0.0：standalone server.js 以 process.env.HOSTNAME 決定 bind 位址，
# Docker 預設把 HOSTNAME 注入為 container id（解析成 eth0 IP），會使 server 只 bind
# 該 IP，loopback healthcheck 於是 Connection refused。釘 0.0.0.0 讓其 bind 全介面。
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000 HOSTNAME=0.0.0.0
RUN addgroup -S app && adduser -S app -G app
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
# standalone 不含 .next/cache；runtime 由 app 寫入 ISR／fetch prerender cache。
# .next 其餘檔案維持 root:root 唯讀，只把 cache 目錄交給 app（最小 ownership 變更）。
RUN mkdir -p .next/cache && chown -R app:app .next/cache
USER app
EXPOSE 3000
# 以 127.0.0.1 明確探測 loopback，避免 busybox wget 對 localhost 先試 ::1（server 只聽 IPv4）。
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s \
    CMD wget -qO- http://127.0.0.1:3000/ || exit 1
CMD ["node", "server.js"]
