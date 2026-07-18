import Link from "next/link";
import { notFound } from "next/navigation";
import { SCENARIOS, VARIANT_LABELS, VARIANTS } from "./lib";

export const metadata = { title: "球員頁 IA 走查（dev only）", robots: { index: false } };

// UX-PLAYER-IA1：tabs／錨點／hybrid 三變體 × 五情境走查入口。
// 查核者：npm run dev 後開 /dev/player-ia，依下方清單做 375px／鍵盤／deep-link 走查。
export default function PlayerIaIndexPage() {
  if (process.env.NODE_ENV === "production") notFound();

  return (
    <main className="mx-auto max-w-3xl space-y-6 px-4 py-6">
      <div>
        <h1 className="text-xl font-bold text-ink">球員頁 IA prototype 走查</h1>
        <p className="mt-1 text-sm text-muted">
          四層骨架（總覽／打法或球路／分項與對戰／生涯）× 三導覽變體 × 五真實 fixture。
          決策文件見 <code className="rounded bg-surface-2 px-1">docs/design/UX-PLAYER-IA1-DECISION.md</code>。
        </p>
      </div>

      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-line text-left text-muted">
            <th className="py-2">情境</th>
            {VARIANTS.map((v) => <th key={v} className="py-2">{VARIANT_LABELS[v]}</th>)}
          </tr>
        </thead>
        <tbody>
          {SCENARIOS.map((s) => (
            <tr key={s.key} className="border-b border-line">
              <td className="py-2 pr-2">
                <div className="text-ink">{s.label}</div>
                <div className="text-xs text-faint">{s.note}</div>
              </td>
              {VARIANTS.map((v) => (
                <td key={v} className="py-2">
                  <Link href={`/dev/player-ia/${v}/${s.key}`} className="text-accent hover:underline">開啟</Link>
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>

      <section className="rounded-xl border border-line bg-surface p-4 text-sm">
        <h2 className="mb-2 font-semibold text-ink">走查清單</h2>
        <ol className="list-decimal space-y-1 pl-5 text-muted">
          <li>375px：導覽是否可及、切層是否掉捲動位置、長頁是否迷路。</li>
          <li>鍵盤：Tab 進入導覽後 ←/→ 切層（tabs/hybrid）；錨點連結 Enter 跳段。</li>
          <li>deep-link：tabs <code className="rounded bg-surface-2 px-1">?layer=career</code>、
            hybrid <code className="rounded bg-surface-2 px-1">?sec=splits</code>、
            錨點 <code className="rounded bg-surface-2 px-1">#career</code>；重新整理後是否落在同層。</li>
          <li>雙棲：role 切換（?role=）是否保留當前層；「打法」是否隨 role 變「球路」。</li>
          <li>缺漏／空／錯誤：二軍 fixture 的逐球缺漏提示；退役 fixture 預設落生涯層；「模擬錯誤態」下各模組獨立降級。</li>
        </ol>
      </section>
    </main>
  );
}
