import Leaderboard, { type Col } from "@/components/leaderboard";
import { api } from "@/lib/api";

export const dynamic = "force-dynamic";

const COLS: Col[] = [
  { key: "name", label: "球員" },
  { key: "team", label: "隊", tone: "dim" },
  { key: "g", label: "G", fmt: "i", tone: "dim" },
  { key: "gs", label: "先發", fmt: "i", tone: "dim" },
  { key: "w", label: "勝", fmt: "i" },
  { key: "l", label: "敗", fmt: "i" },
  { key: "sv", label: "救援", fmt: "i" },
  { key: "hld", label: "中繼", fmt: "i" },
  { key: "ip", label: "局數", fmt: "f1" },
  { key: "era", label: "防禦率", fmt: "f2", tone: "accent" },
  { key: "whip", label: "WHIP", fmt: "f2" },
  { key: "k9", label: "K9", fmt: "f2", tone: "dim" },
];

export default async function PitchersPage() {
  const { season, items } = await api.pitchingLeaders("era");

  return (
    <div>
      <header className="mb-5">
        <h1 className="text-2xl font-bold">{season} 球季 · 投手排行</h1>
        <p className="mt-2 text-sm text-white/50">
          全名單本季投手。點欄位標題排序（再點一次反向），可依球隊篩選。K9 = 三振 × 9 ÷ 局數。
        </p>
      </header>

      <Leaderboard
        rows={items}
        cols={COLS}
        defaultSort="era"
        defaultDir={1}
        filters={[{ key: "team", label: "球隊" }]}
      />
    </div>
  );
}
