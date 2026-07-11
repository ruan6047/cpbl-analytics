import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // 子專案掛在子網域根路徑，毋需 basePath
  output: "standalone",
  // build 與 dev 共用 .next 會互相污染 chunk（查核者跑 build 時 dev 讀到對不上的
  // ./NNN.js → Runtime Error）。用 NEXT_DIST_DIR 讓「驗證用 build」寫到獨立目錄，
  // 永不碰 dev 的 .next。見 package.json 的 build:check。
  distDir: process.env.NEXT_DIST_DIR || ".next",
};

export default nextConfig;
