import Leaderboard, { type Col } from "@/components/leaderboard";
import { api } from "@/lib/api";

export const dynamic = "force-dynamic";

const COLS: Col[] = [
  { key: "name", label: "球員" },
  { key: "team", label: "隊", tone: "dim" },
  { key: "pos", label: "守位" },
  { key: "g", label: "G", fmt: "i", tone: "dim" },
  { key: "tc", label: "守備機會", fmt: "i" },
  { key: "po", label: "刺殺", fmt: "i" },
  { key: "a", label: "助殺", fmt: "i" },
  { key: "e", label: "失誤", fmt: "i", tone: "warn" },
  { key: "dp", label: "雙殺", fmt: "i" },
  { key: "fpct", label: "守備率", fmt: "f3", tone: "accent" },
];

export default async function FieldingPage() {
  const { season, items } = await api.fielding("tc");

  return (
    <div>
      <header className="mb-5">
        <h1 className="text-2xl font-bold">{season} 球季 · 守備數據</h1>
        <p className="mt-2 text-sm text-white/50">
          逐守備位置統計。點欄位標題排序，可依球隊與守位篩選。守備率 = (刺殺+助殺) ÷ 守備機會。
        </p>
      </header>

      <Leaderboard
        rows={items}
        cols={COLS}
        defaultSort="tc"
        filters={[
          { key: "team", label: "球隊" },
          { key: "pos", label: "守位" },
        ]}
      />
    </div>
  );
}
