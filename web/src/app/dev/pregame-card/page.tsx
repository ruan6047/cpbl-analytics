import { notFound } from "next/navigation";
import { PregameCard } from "@/components/pregame-card";
import { PREGAME_FIXTURES } from "@/lib/pregame-card-fixtures";
import { resolvePregameCard } from "@/lib/pregame-card";

export const metadata = { title: "PregameCard 走查（dev only）", robots: { index: false } };

// UX-OUTCOME-HOME 五態走查頁：只在開發環境存在（fixture 是假資料，不得公開）。
// 查核者：npm run dev 後開 /dev/pregame-card，做 375px 與鍵盤走查。
export default function PregameCardDevPage() {
  if (process.env.NODE_ENV === "production") notFound();

  return (
    <main className="mx-auto max-w-md space-y-4 p-4">
      <h1 className="text-lg font-bold text-ink">PregameCard 五態走查</h1>
      <p className="text-xs text-muted">
        fixture 為假資料；available 的 payload 內含 model_interval_90，用以驗證卡片不渲染區間。
      </p>
      {Object.entries(PREGAME_FIXTURES).map(([name, fixture]) => (
        <section key={name} className="card space-y-2 p-4">
          <h2 className="font-mono text-xs text-faint">{name}</h2>
          {/* 模擬外層賽程卡：對戰列永遠在，PregameCard 只是附掛模組（不阻塞驗收）。 */}
          <div className="flex items-baseline justify-between text-sm text-ink">
            <span>中信兄弟 @ 樂天桃猿</span>
            <span className="text-xs text-faint">18:35 桃園</span>
          </div>
          <PregameCard model={resolvePregameCard(fixture)} homeName="樂天桃猿" />
        </section>
      ))}
    </main>
  );
}
