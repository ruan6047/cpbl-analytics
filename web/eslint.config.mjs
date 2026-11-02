// ESLint 9 flat config。eslint-config-next 15 仍是舊式（eslintrc）設定，透過 FlatCompat 載入；
// Next 16 起 `next lint` 移除，故 lint 指令直接呼叫 eslint（package.json 的 "lint"）。
// 規則集只用 next/core-web-vitals：2026-11-02 首次導入時全庫 3 個 error（已修）＋3 個
// react-hooks/exhaustive-deps warning（保留為 warning，不在本次盲改 hooks 依賴）。
import { FlatCompat } from "@eslint/eslintrc";

const compat = new FlatCompat({ baseDirectory: import.meta.dirname });

export default [
  ...compat.extends("next/core-web-vitals"),
  { ignores: [".next/**", ".next-check/**", "node_modules/**", "out/**", "next-env.d.ts"] },
];
