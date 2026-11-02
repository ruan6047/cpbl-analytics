// ESLint 9 flat config。eslint-config-next 16 起原生輸出 flat config（直接 import 展開），
// 不再需要 @eslint/eslintrc 的 FlatCompat（15 時代的包法在 16 下會拋
// `TypeError: Converting circular structure to JSON`，#419 探針實證）。
// Next 16 的 `next lint` 已移除、`next build` 也不再 lint，故 lint 只剩 package.json 的 "lint"
// 直接呼叫 eslint 這一道（CI web job 跑）。
// 規則集只用 next/core-web-vitals：2026-11-02 首次導入時全庫 3 個 error（已修）＋3 個
// react-hooks/exhaustive-deps warning（保留為 warning，不在本次盲改 hooks 依賴）。
import nextVitals from "eslint-config-next/core-web-vitals";

export default [
  ...nextVitals,
  { ignores: [".next/**", ".next-check/**", "node_modules/**", "out/**", "next-env.d.ts"] },
  {
    // eslint-config-next 16 帶入 eslint-plugin-react-hooks 7 的 React Compiler 規則（預設 error）。
    // 本專案未啟用 React Compiler；#419 升級時下列三條命中 49 處／22 檔，全是既有寫法
    // （effect 內同步 setState、render 期讀 ref、render 後改局部變數），不是本次升級引入的缺陷。
    // 依需求方裁定（#419 規劃確認）：本卡只把這三條降為 warn、⛔ 不改寫法，修正另案處理。
    // 其餘 compiler 規則（purity、set-state-in-render、globals…）目前 0 命中，維持 error 作新碼守衛。
    rules: {
      "react-hooks/set-state-in-effect": "warn",
      "react-hooks/refs": "warn",
      "react-hooks/immutability": "warn",
    },
  },
];
