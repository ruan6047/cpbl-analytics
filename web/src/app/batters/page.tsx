import Leaderboard, { type Col } from "@/components/leaderboard";
import { api } from "@/lib/api";

export const dynamic = "force-dynamic";

const COLS: Col[] = [
  { key: "name", label: "球員" },
  { key: "team", label: "隊", tone: "dim" },
  { key: "g", label: "G", fmt: "i", tone: "dim" },
  { key: "pa", label: "PA", fmt: "i" },
  { key: "ab", label: "AB", fmt: "i", tone: "dim" },
  { key: "r", label: "R", fmt: "i" },
  { key: "h", label: "H", fmt: "i" },
  { key: "b2", label: "2B", fmt: "i", tone: "dim" },
  { key: "b3", label: "3B", fmt: "i", tone: "dim" },
  { key: "hr", label: "HR", fmt: "i" },
  { key: "rbi", label: "RBI", fmt: "i" },
  { key: "bb", label: "BB", fmt: "i", tone: "dim" },
  { key: "so", label: "SO", fmt: "i", tone: "dim" },
  { key: "sb", label: "SB", fmt: "i", tone: "accent" },
  { key: "cs", label: "CS", fmt: "i", tone: "dim" },
  { key: "avg", label: "打擊率", fmt: "f3" },
  { key: "obp", label: "上壘率", fmt: "f3" },
  { key: "slg", label: "長打率", fmt: "f3" },
  { key: "ops", label: "OPS", fmt: "f3", tone: "accent" },
];

export default async function BattersPage() {
  const { season, items } = await api.battingLeaders("ops");

  return (
    <div>
      <header className="mb-5">
        <h1 className="text-2xl font-bold">{season} 球季 · 打者排行</h1>
        <p className="mt-2 text-sm text-white/50">
          全名單本季打者。點欄位標題排序（再點一次反向），可依球隊篩選。
        </p>
      </header>

      <Leaderboard
        rows={items}
        cols={COLS}
        defaultSort="ops"
        filters={[{ key: "team", label: "球隊" }]}
      />
    </div>
  );
}
