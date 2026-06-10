import { api } from "@/lib/api";

export default async function Home() {
  const { season, standings } = await api.standings();

  return (
    <div>
      <header className="mb-6">
        <h1 className="text-2xl font-bold">{season} 球季 · 本季戰績</h1>
        <p className="mt-2 text-sm text-white/50">
          由官網逐場結果即時彙整(資料更新至最近一次爬蟲)。場均得分 / 失分為攻守指標。
        </p>
      </header>

      <div className="overflow-x-auto rounded-xl border border-white/10">
        <table className="w-full text-sm">
          <thead className="bg-white/5 text-left text-white/50">
            <tr>
              <th className="px-3 py-3 font-medium">#</th>
              <th className="px-3 py-3 font-medium">球隊</th>
              <th className="px-3 py-3 text-right font-medium">勝–敗</th>
              <th className="px-3 py-3 text-right font-medium">勝率</th>
              <th className="px-3 py-3 text-right font-medium">得失差</th>
              <th className="px-3 py-3 text-right font-medium" title="團隊整體攻擊指數">團隊OPS</th>
              <th className="px-3 py-3 text-right font-medium" title="團隊防禦率">ERA</th>
              <th className="px-3 py-3 text-right font-medium" title="團隊每局被上壘率">WHIP</th>
              <th className="px-3 py-3 text-right font-medium">近10</th>
            </tr>
          </thead>
          <tbody className="font-mono tabular-nums">
            {standings.map((t, i) => (
              <tr key={t.code} className="border-t border-white/5 hover:bg-white/5">
                <td className="px-3 py-3 text-white/40">{i + 1}</td>
                <td className="px-3 py-3 font-sans">{t.name}</td>
                <td className="px-3 py-3 text-right">
                  {t.w}–{t.l}
                </td>
                <td className="px-3 py-3 text-right text-emerald-400">{t.win_pct.toFixed(3)}</td>
                <td
                  className={`px-3 py-3 text-right ${t.run_diff >= 0 ? "text-emerald-400/80" : "text-rose-400/80"}`}
                >
                  {t.run_diff >= 0 ? "+" : ""}
                  {t.run_diff.toFixed(2)}
                </td>
                <td className="px-3 py-3 text-right">{t.ops?.toFixed(3) ?? "—"}</td>
                <td className="px-3 py-3 text-right">{t.era?.toFixed(2) ?? "—"}</td>
                <td className="px-3 py-3 text-right">{t.whip?.toFixed(2) ?? "—"}</td>
                <td className="px-3 py-3 text-right text-white/50">{t.form}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
