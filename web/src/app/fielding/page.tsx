import Leaderboard, { type Col } from "@/components/leaderboard";
import { api } from "@/lib/api";

export const dynamic = "force-dynamic";

const COLS: Col[] = [
  { key: "name", label: "球員", tip: "球員姓名（點擊看個人頁）", link: { base: "/players/", idKey: "player_id" } },
  { key: "team", label: "隊", team: true, tip: "所屬球隊" },
  { key: "pos", label: "守位", tip: "守備位置" },
  { key: "g", label: "出賽", fmt: "i", tone: "dim", tip: "該守位出賽場數（G）" },
  { key: "tc", label: "守備機會", fmt: "i", tip: "守備機會 TC = 刺殺＋助殺＋失誤" },
  { key: "po", label: "刺殺", fmt: "i", tip: "刺殺 PO：直接使打者/跑者出局" },
  { key: "a", label: "助殺", fmt: "i", tip: "助殺 A：傳球協助使對方出局" },
  { key: "e", label: "失誤", fmt: "i", tone: "warn", tip: "失誤 E" },
  { key: "dp", label: "雙殺", fmt: "i", tip: "參與的雙殺次數" },
  { key: "fpct", label: "守備率", fmt: "f3", tone: "accent", tip: "守備率 = (刺殺＋助殺) ÷ 守備機會" },
];

export default async function FieldingPage() {
  const { season, items } = await api.fielding("tc");

  return (
    <div>
      <header className="mb-5">
        <h1 className="text-2xl font-bold">{season} 球季 · 守備數據</h1>
        <p className="mt-2 text-sm text-muted">
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
