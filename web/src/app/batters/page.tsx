import Leaderboard, { type Col } from "@/components/leaderboard";
import { api } from "@/lib/api";

export const dynamic = "force-dynamic";

const COLS: Col[] = [
  { key: "name", label: "球員", tip: "球員姓名（點擊看個人頁）", link: { base: "/players/", idKey: "player_id" } },
  { key: "team", label: "隊", tone: "dim", tip: "所屬球隊" },
  { key: "g", label: "出賽", fmt: "i", tone: "dim", tip: "出賽場數（G）" },
  { key: "pa", label: "打席", fmt: "i", tip: "打席（PA）：打數＋四壞＋死球＋犧牲打／高飛犧牲" },
  { key: "ab", label: "打數", fmt: "i", tone: "dim", tip: "打數（AB）：不含四壞、死球、犧牲" },
  { key: "r", label: "得分", fmt: "i", tip: "得分（R）" },
  { key: "h", label: "安打", fmt: "i", tip: "安打總數（H）" },
  { key: "b2", label: "二安", fmt: "i", tone: "dim", tip: "二壘安打（2B）" },
  { key: "b3", label: "三安", fmt: "i", tone: "dim", tip: "三壘安打（3B）" },
  { key: "hr", label: "全壘打", fmt: "i", tip: "全壘打（HR）" },
  { key: "rbi", label: "打點", fmt: "i", tip: "打點（RBI）：因該打席而得分的隊友數" },
  { key: "bb", label: "四壞", fmt: "i", tone: "dim", tip: "四壞球／保送（BB）" },
  { key: "so", label: "三振", fmt: "i", tone: "dim", tip: "被三振次數（SO）" },
  { key: "sb", label: "盜壘", fmt: "i", tone: "accent", tip: "盜壘成功（SB）" },
  { key: "cs", label: "盜失", fmt: "i", tone: "dim", tip: "盜壘失敗／被刺殺（CS）" },
  { key: "avg", label: "打擊率", fmt: "f3", tip: "打擊率 AVG = 安打 ÷ 打數" },
  { key: "obp", label: "上壘率", fmt: "f3", tip: "上壘率 OBP = (安打＋四壞＋死球) ÷ (打數＋四壞＋死球＋高飛犧牲)" },
  { key: "slg", label: "長打率", fmt: "f3", tip: "長打率 SLG = 壘打數 ÷ 打數" },
  { key: "ops", label: "OPS", fmt: "f3", tone: "accent", tip: "整體攻擊指數 OPS = 上壘率＋長打率" },
];

export default async function BattersPage() {
  const { season, items } = await api.battingLeaders("ops");

  return (
    <div>
      <header className="mb-5">
        <h1 className="text-2xl font-bold">{season} 球季 · 打者排行</h1>
        <p className="mt-2 text-sm text-muted">
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
