// 元件測試用的 module hooks：讓 `node --test` 直接載入 `.tsx`。
//
// 為什麼不引入 vitest/jest：本專案 364 條測試已經跑在 node 內建 runner 上（type
// stripping），再疊一個 runner 等於兩套設定、兩套 mock 語意。這裡只補 node 唯一缺的
// 能力——**JSX 轉譯**與 `@/*` 路徑別名——其餘（glob、assert、reporter）沿用內建。
//
// 轉譯器用 **已在 devDependencies 的 typescript**（`transpileModule`，不型別檢查），
// 所以本檔的代價是 0 個新依賴。`.ts` 不攔截，仍走 node 原生 type stripping。
import { createRequire, registerHooks } from "node:module";
import { existsSync } from "node:fs";
import { fileURLToPath, pathToFileURL } from "node:url";
import path from "node:path";

const SRC = pathToFileURL(path.join(import.meta.dirname, "..", "src") + path.sep).href;
const EXTS = [".tsx", ".ts", "/index.tsx", "/index.ts"];

/** 補副檔名：`.tsx` 內的 `./tooltip`、`@/components/ui` 在 node ESM 是解析不到的。 */
function withExt(url) {
  if (/\.[a-z]+$/i.test(url) && existsSync(fileURLToPath(url))) return url;
  for (const ext of EXTS) {
    if (existsSync(fileURLToPath(url + ext))) return url + ext;
  }
  return null;
}

/** 只有 `.tsx` 要由本檔宣告 format（node 不認這個副檔名）；`.ts` 交回 node，
 *  讓它照原本的 type stripping 走——既有 364 條測試的載入路徑一格都不改。 */
function resolved(url, context, nextResolve) {
  if (url.endsWith(".tsx")) return { url, format: "module", shortCircuit: true };
  return nextResolve(url, context);
}

const require = createRequire(import.meta.url);
let ts = null;

registerHooks({
  resolve(specifier, context, nextResolve) {
    if (specifier.startsWith("@/")) {
      const url = withExt(SRC + specifier.slice(2));
      if (url) return resolved(url, context, nextResolve);
    }
    if (specifier.startsWith(".") && context.parentURL?.endsWith(".tsx")) {
      const url = withExt(new URL(specifier, context.parentURL).href);
      if (url) return resolved(url, context, nextResolve);
    }
    try {
      return nextResolve(specifier, context);
    } catch (err) {
      // `next/link` 這類 subpath 在 Next 的 package.json 沒有 exports 對應，靠 bundler
      // 補 `.js`。這裡照做，載到的仍是**真的** next/link，不是 stub。刻意只放行 `next/`：
      // 其他套件缺模組時錯誤照原樣拋出，不被這條退路蓋成另一個訊息。
      if (err?.code === "ERR_MODULE_NOT_FOUND" && specifier.startsWith("next/")) {
        return nextResolve(specifier + ".js", context);
      }
      throw err;
    }
  },
  load(url, context, nextLoad) {
    if (!url.endsWith(".tsx")) return nextLoad(url, context);
    const raw = nextLoad(url, { ...context, format: "module" });
    ts ??= require("typescript"); // 只有真的載到 .tsx 才付 typescript 的載入成本
    const out = ts.transpileModule(String(raw.source), {
      fileName: fileURLToPath(url),
      compilerOptions: {
        jsx: ts.JsxEmit.ReactJSX,
        module: ts.ModuleKind.ESNext,
        target: ts.ScriptTarget.ES2022,
        verbatimModuleSyntax: false,
      },
    });
    return { format: "module", source: out.outputText, shortCircuit: true };
  },
});
