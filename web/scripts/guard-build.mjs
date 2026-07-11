// prebuild 守衛：若 :3000 有 dev server 在跑，中止 `npm run build`。
// 原因：next build 與 next dev 共用 web/.next；build 覆寫 .next 後 dev 讀到對不上的
// chunk → 全站 Internal Server Error。此守衛只綁 `build`（npm 的 prebuild），
// 不綁 `build:check`（寫獨立 .next-check，本就安全）。CI/生產無 dev 在跑 → 正常放行。
import net from "node:net";

const PORT = Number(process.env.PORT) || 3000;

const sock = net.connect(PORT, "127.0.0.1");
sock.setTimeout(1500);
sock.on("connect", () => {
  sock.destroy();
  console.error(
    `\n⛔ 偵測到 dev server 正在 :${PORT} 運行。\n` +
    `   npm run build 會覆寫其 .next → dev 全站 Internal Server Error（chunk 對不上）。\n` +
    `   請二選一：\n` +
    `     • 停掉 dev 後再 build，或\n` +
    `     • 改用「npm run build:check」（寫獨立 .next-check，完全不影響 dev）。\n`,
  );
  process.exit(1);
});
const ok = () => process.exit(0); // 沒人聽 :3000（或逾時）→ 正常 build
sock.on("error", ok);
sock.on("timeout", () => { sock.destroy(); ok(); });
