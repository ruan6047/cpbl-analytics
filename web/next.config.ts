import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // 子專案掛在子網域根路徑，毋需 basePath
  output: "standalone",
  // build 與 dev 共用 .next 會互相污染 chunk（查核者跑 build 時 dev 讀到對不上的
  // ./NNN.js → Runtime Error）。用 NEXT_DIST_DIR 讓「驗證用 build」寫到獨立目錄，
  // 永不碰 dev 的 .next。見 package.json 的 build:check。
  // 註（Next 16，#419）：`next dev` 現在寫 `.next/dev/`（與 `next build` 的 `.next/` 分離），
  // 守衛前提弱化但無害，distDir 技巧照舊保留。
  // `next-env.d.ts` 在 16 下由 `next dev`／`next build`／`next typegen` 各自改寫成不同內容
  // （dev → `./.next/dev/types/…`、build → `./<distDir>/types/…`、typegen → `./.next/types/…`），
  // 15 時代「git 基準＝dev 輸出、build:check 結束還原」的作法已無法維持，故依官方 16 文件
  // 改為不入版控（web/.gitignore），build:check 也不再還原它。
  // CI 是 `npm ci` 後 `npx next typegen` 再 `npx tsc --noEmit`（未先 build）：typegen 產生
  // next-env.d.ts 與 .next/types，補回 `/// <reference types="next" />` 帶進來的 Next 全域型別。
  distDir: process.env.NEXT_DIST_DIR || ".next",
};

export default nextConfig;
