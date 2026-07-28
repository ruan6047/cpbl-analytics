import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // 子專案掛在子網域根路徑，毋需 basePath
  output: "standalone",
  // build 與 dev 共用 .next 會互相污染 chunk（查核者跑 build 時 dev 讀到對不上的
  // ./NNN.js → Runtime Error）。用 NEXT_DIST_DIR 讓「驗證用 build」寫到獨立目錄，
  // 永不碰 dev 的 .next。見 package.json 的 build:check。
  // 註：`next build` 會依 distDir 改寫 web/next-env.d.ts 的 `/// <reference path>` 那一行，
  // 使 `.next` ↔ `.next-check` 來回翻轉、每次驗證後 worktree 就變髒（實際造成過交付時的
  // 「worktree clean」宣稱不成立）。該行在本專案**無作用**——tsconfig 的 include 已同時列了
  // `.next/types/**/*.ts` 與 `.next-check/types/**/*.ts`，且兩者皆 gitignore、乾淨 checkout 上都不存在。
  // 故由 build:check 於結束時還原該檔（保留原 exit code），不改 gitignore——
  // CI 是 `npm ci` 後直接 `npx tsc --noEmit`（未先 build），少了 next-env.d.ts 會失去
  // `/// <reference types="next" />` 帶進來的 Next 全域型別。
  distDir: process.env.NEXT_DIST_DIR || ".next",
};

export default nextConfig;
