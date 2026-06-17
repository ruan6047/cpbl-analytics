import Leaderboard, { type Col } from "@/components/leaderboard";
import { api } from "@/lib/api";

export const dynamic = "force-dynamic";

const COLS: Col[] = [
  { key: "name", label: "球員", tip: "球員姓名（點擊看個人頁）", link: { base: "/players/", idKey: "player_id" } },
  { key: "team", label: "隊", tone: "dim", tip: "所屬球隊" },
  { key: "g", label: "出賽", fmt: "i", tone: "dim", tip: "出賽場數（G）" },
  { key: "gs", label: "先發", fmt: "i", tone: "dim", tip: "先發場數" },
  { key: "cg", label: "完投", fmt: "i", tone: "dim", tip: "完投：先發且投完全場" },
  { key: "sho", label: "完封", fmt: "i", tone: "dim", tip: "完封：完投且未失分" },
  { key: "w", label: "勝", fmt: "i", tip: "勝場" },
  { key: "l", label: "敗", fmt: "i", tip: "敗場" },
  { key: "sv", label: "救援", fmt: "i", tip: "救援成功 SV" },
  { key: "hld", label: "中繼", fmt: "i", tip: "中繼成功 HLD" },
  { key: "ip", label: "局數", fmt: "f1", tip: "投球局數 IP（.1=⅓局、.2=⅔局）" },
  { key: "era", label: "防禦率", fmt: "f2", tone: "accent", tip: "防禦率 ERA = 自責分 ×9 ÷ 投球局數" },
  { key: "whip", label: "WHIP", fmt: "f2", tip: "每局被上壘率 = (被安打＋四壞) ÷ 投球局數" },
  { key: "k9", label: "K9", fmt: "f2", tone: "dim", tip: "每九局奪三振 = 三振 ×9 ÷ 投球局數" },
  { key: "h", label: "被安", fmt: "i", tone: "dim", tip: "被安打" },
  { key: "hr", label: "被轟", fmt: "i", tone: "dim", tip: "被全壘打" },
  { key: "bb", label: "四壞", fmt: "i", tone: "dim", tip: "投出的四壞球（保送）" },
  { key: "ibb", label: "故四", fmt: "i", tone: "dim", tip: "故意四壞" },
  { key: "hbp", label: "死球", fmt: "i", tone: "dim", tip: "觸身球（死球）" },
  { key: "so", label: "三振", fmt: "i", tip: "奪三振" },
  { key: "wp", label: "暴投", fmt: "i", tone: "dim", tip: "暴投" },
  { key: "bk", label: "犯規", fmt: "i", tone: "dim", tip: "投手犯規（balk）" },
  { key: "r", label: "失分", fmt: "i", tone: "dim", tip: "失分（含非自責）" },
  { key: "er", label: "自責", fmt: "i", tone: "warn", tip: "自責分：計入防禦率的失分" },
  { key: "goao", label: "滾飛比", fmt: "f2", tone: "dim", tip: "滾飛出局比 = 滾地出局 ÷ 高飛出局" },
];

export default async function PitchersPage() {
  const { season, items } = await api.pitchingLeaders("era");

  return (
    <div>
      <header className="mb-5">
        <h1 className="text-2xl font-bold">{season} 球季 · 投手排行</h1>
        <p className="mt-2 text-sm text-muted">
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
