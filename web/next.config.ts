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
  // Next 16 的 `next dev` 偵測到 AI coding agent 環境時會自動寫入 web/AGENTS.md（Next 版本綁定的
  // agent 指示區塊）；本 repo 以根目錄 AGENTS.md／CLAUDE.md 為唯一規範來源，不要第二份由工具改寫、
  // 隨版本變動的巢狀指示檔，故關閉（需求方 #419 裁定）。只影響 dev 的這個副作用，不改頁面與建置。
  agentRules: false,
};

export default nextConfig;
