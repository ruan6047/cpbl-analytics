import { AwardRaces, type Cat } from "@/components/award-races";
import Leaderboard, { type Col } from "@/components/leaderboard";
import { RankNav, type RankView } from "@/components/rank-nav";
import { Eyebrow } from "@/components/ui";
import { api } from "@/lib/api";

export const dynamic = "force-dynamic";

// 本季獎項競逐類別（前五）：計數型無門檻；rate 型套規定打席。
const AWARD_CATS: Cat[] = [
  { key: "hr", label: "全壘打 (HR)", fmt: "i" },
  { key: "rbi", label: "打點 (RBI)", fmt: "i" },
  { key: "h", label: "安打 (H)", fmt: "i" },
  { key: "sb", label: "盜壘 (SB)", fmt: "i" },
  { key: "avg", label: "打擊率 (AVG)", fmt: "f3", qual: true },
  { key: "ops", label: "OPS", fmt: "f3", qual: true },
];

// 精簡檢視（primary，§5.6）＝球員(隊徽＋守位標籤併入名字欄)·打席·安打·全壘打·打點·打擊率·OPS·OPS+（8 欄）；
// 其餘欄由「完整欄位」切換顯示。手機（mobileHide）再收打席/安打/全壘打/打點/OPS+，留主指標 OPS＋AVG。
const COLS: Col[] = [
  { key: "name", label: "球員", tip: "球員姓名（點擊看個人頁）", link: { base: "/players/", idKey: "player_id" }, teamKey: "team", subChipKey: "pos", primary: true },
  { key: "g", label: "出賽", fmt: "i", tone: "dim", tip: "出賽場數（G）" },
  { key: "pa", label: "打席", fmt: "i", tone: "dim", primary: true, mobileHide: true, tip: "打席（PA）：打數＋四壞＋死球＋犧牲打／高飛犧牲；亦為規定打席門檻的計量" },
  { key: "ab", label: "打數", fmt: "i", tone: "dim", tip: "打數（AB）：不含四壞、死球、犧牲" },
  { key: "r", label: "得分", fmt: "i", tip: "得分（R）" },
  { key: "h", label: "安打", fmt: "i", bar: true, primary: true, mobileHide: true, tip: "安打總數（H）" },
  { key: "b2", label: "二安", fmt: "i", tone: "dim", tip: "二壘安打（2B）" },
  { key: "b3", label: "三安", fmt: "i", tone: "dim", tip: "三壘安打（3B）" },
  { key: "hr", label: "全壘打", fmt: "i", bar: true, primary: true, mobileHide: true, tip: "全壘打（HR）" },
  { key: "rbi", label: "打點", fmt: "i", bar: true, primary: true, mobileHide: true, tip: "打點（RBI）：因該打席而得分的隊友數" },
  { key: "bb", label: "四壞", fmt: "i", tone: "dim", tip: "四壞球／保送（BB）" },
  { key: "so", label: "三振", fmt: "i", tone: "dim", tip: "被三振次數（SO）" },
  { key: "sb", label: "盜壘", fmt: "i", tone: "accent", tip: "盜壘成功（SB）" },
  { key: "cs", label: "盜失", fmt: "i", tone: "dim", tip: "盜壘失敗／被刺殺（CS）" },
  { key: "avg", label: "打擊率", fmt: "f3", bar: true, primary: true, rate: true, tip: "打擊率 AVG = 安打 ÷ 打數" },
  { key: "obp", label: "上壘率", fmt: "f3", bar: true, rate: true, tip: "上壘率 OBP = (安打＋四壞＋死球) ÷ (打數＋四壞＋死球＋高飛犧牲)" },
  { key: "slg", label: "長打率", fmt: "f3", bar: true, rate: true, tip: "長打率 SLG = 壘打數 ÷ 打數" },
  { key: "ops", label: "OPS", fmt: "f3", bar: true, primary: true, rate: true, tone: "accent", tip: "整體攻擊指數 OPS = 上壘率＋長打率" },
  { key: "ops_plus", label: "OPS+", fmt: "i", bar: true, primary: true, rate: true, mobileHide: true, tip: "OPS+（僅一軍）：100 = 聯盟平均，>100 優於聯盟（季聯盟基準，非球場校正）" },
];

export default async function BattersPage({ searchParams }: { searchParams: Promise<{ year?: string; kind?: string; view?: string }> }) {
  const { year: yp, kind: kp, view: vp } = await searchParams;
  const kind = kp === "D" ? "D" : "A";
  // 主內容視圖（§4.3 第二例）：完整清單（預設；無 view 參數向後相容）↔ 獎項排行榜分頁。
  const view: RankView = vp === "awards" ? "awards" : "list";
  const { years } = await api.seasons(kind);
  const currentYear = years[0] ?? new Date().getFullYear();
  const selectedYear = yp ? Number(yp) : currentYear;
  const isCurrent = selectedYear === currentYear && kind === "A";
  const { season, items } = await api.battingLeaders("ops", { kind, year: isCurrent ? undefined : selectedYear });
  // 規定打席≈球隊出賽×3.1（率值榜門檻，AwardRaces 與排行表共用）。
  const teamG = Math.max(0, ...items.map((r) => Number(r.g ?? 0)));
  const qual = Math.round(3.1 * teamG);

  return (
    <div>
      <header className="mb-6">
        <Eyebrow className="mb-2">排行中心・打者</Eyebrow>
        <h1 className="text-2xl font-extrabold tracking-tight text-ink">{season} 球季 · {kind === "D" ? "二軍" : ""}打者排行</h1>
        <p className="mt-1.5 text-sm text-muted">
          {kind === "D" || !isCurrent ? "由逐場/逐年成績彙整（二軍逐打席自 2018 起）。" : "全名單本季打者。"}
          預設顯示主要欄位，點「完整欄位」看全部；點欄位標題排序（再點一次反向），可依球隊篩選。
        </p>
      </header>

      <RankNav role="batting" view={view} kind={kind} years={years} selectedYear={selectedYear} />

      {view === "awards" ? (
        <AwardRaces rows={items} cats={AWARD_CATS} qualKey="pa" qualMin={qual}
          note={`規定打席約 ${qual}（打擊率/OPS 套用）。`} />
      ) : (
        <section aria-labelledby="batting-leaderboard">
          <Eyebrow className="mb-2">完整排名・共 {items.length} 人</Eyebrow>
          <h2 id="batting-leaderboard" className="sr-only">打者完整排名</h2>
          <Leaderboard
            rows={items}
            cols={COLS}
            defaultSort="ops"
            filters={[{ key: "team", label: "球隊" }, { key: "pos", label: "守位" }]}
            qualKey="pa"
            qualMin={qual}
          />
        </section>
      )}
    </div>
  );
}
