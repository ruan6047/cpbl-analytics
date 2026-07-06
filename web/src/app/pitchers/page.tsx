import { AwardRaces, type Cat } from "@/components/award-races";
import Leaderboard, { type Col } from "@/components/leaderboard";
import { LevelYearNav } from "@/components/level-year-nav";
import { api } from "@/lib/api";

export const dynamic = "force-dynamic";

// 本季獎項競逐：勝投/三振/救援無門檻；防禦率/WHIP/K9 套規定投球局數（越低越好者 asc）。
const AWARD_CATS: Cat[] = [
  { key: "w", label: "勝投 (W)", fmt: "i" },
  { key: "so", label: "三振 (SO)", fmt: "i" },
  { key: "sv", label: "救援 (SV)", fmt: "i" },
  { key: "era", label: "防禦率 (ERA)", fmt: "f2", dir: "asc", qual: true },
  { key: "whip", label: "WHIP", fmt: "f2", dir: "asc", qual: true },
  { key: "k9", label: "K9", fmt: "f2", qual: true },
];

// 投手角色：先發（先發場數佔半數以上）/ 後援（救援>中繼，終結者傾向）/ 中繼（其餘救援投手）
function pitcherRole(r: Record<string, number | string | null>): string | null {
  const g = Number(r.g ?? 0), gs = Number(r.gs ?? 0), sv = Number(r.sv ?? 0), hld = Number(r.hld ?? 0);
  if (g === 0) return null;
  if (gs * 2 >= g) return "先發";
  if (sv > hld) return "後援";
  return "中繼";
}

const COLS: Col[] = [
  { key: "name", label: "球員", tip: "球員姓名（點擊看個人頁）", link: { base: "/players/", idKey: "player_id" } },
  { key: "team", label: "隊", team: true, tip: "所屬球隊" },
  { key: "role", label: "角色", sortable: false, tip: "先發＝先發場數佔半數以上；後援＝救援>中繼（終結者傾向）；中繼＝其餘後援投手" },
  { key: "g", label: "出賽", fmt: "i", tone: "dim", tip: "出賽場數（G）" },
  { key: "gs", label: "先發", fmt: "i", tone: "dim", tip: "先發場數" },
  { key: "cg", label: "完投", fmt: "i", tone: "dim", tip: "完投：先發且投完全場" },
  { key: "sho", label: "完封", fmt: "i", tone: "dim", tip: "完封：完投且未失分" },
  { key: "w", label: "勝", fmt: "i", bar: true, tip: "勝場" },
  { key: "l", label: "敗", fmt: "i", tip: "敗場" },
  { key: "sv", label: "救援", fmt: "i", bar: true, tip: "救援成功 SV" },
  { key: "hld", label: "中繼", fmt: "i", tip: "中繼成功 HLD" },
  { key: "ip", label: "局數", fmt: "ip", tip: "投球局數 IP（分數顯示，⅓=1出局、⅔=2出局）" },
  { key: "era", label: "防禦率", fmt: "f2", bar: true, lowerBetter: true, tone: "accent", tip: "防禦率 ERA = 自責分 ×9 ÷ 投球局數" },
  { key: "whip", label: "WHIP", fmt: "f2", bar: true, lowerBetter: true, tip: "每局被上壘率 = (被安打＋四壞) ÷ 投球局數" },
  { key: "k9", label: "K9", fmt: "f2", bar: true, tip: "每九局奪三振 = 三振 ×9 ÷ 投球局數" },
  { key: "h", label: "被安", fmt: "i", tone: "dim", tip: "被安打" },
  { key: "hr", label: "被轟", fmt: "i", tone: "dim", tip: "被全壘打" },
  { key: "bb", label: "四壞", fmt: "i", tone: "dim", tip: "投出的四壞球（保送）" },
  { key: "ibb", label: "故四", fmt: "i", tone: "dim", tip: "故意四壞" },
  { key: "hbp", label: "死球", fmt: "i", tone: "dim", tip: "觸身球（死球）" },
  { key: "so", label: "三振", fmt: "i", bar: true, tip: "奪三振" },
  { key: "wp", label: "暴投", fmt: "i", tone: "dim", tip: "暴投" },
  { key: "bk", label: "犯規", fmt: "i", tone: "dim", tip: "投手犯規（balk）" },
  { key: "r", label: "失分", fmt: "i", tone: "dim", tip: "失分（含非自責）" },
  { key: "er", label: "自責", fmt: "i", tone: "warn", tip: "自責分：計入防禦率的失分" },
  { key: "goao", label: "滾飛比", fmt: "f2", tone: "dim", tip: "滾飛出局比 = 滾地出局 ÷ 高飛出局" },
];

export default async function PitchersPage({ searchParams }: { searchParams: Promise<{ year?: string; kind?: string }> }) {
  const { year: yp, kind: kp } = await searchParams;
  const kind = kp === "D" ? "D" : "A";
  const { years } = await api.seasons(kind);
  const currentYear = years[0] ?? new Date().getFullYear();
  const selectedYear = yp ? Number(yp) : currentYear;
  const isCurrent = selectedYear === currentYear && kind === "A";
  const { season, items } = await api.pitchingLeaders("era", { kind, year: isCurrent ? undefined : selectedYear });
  const rows = items.map((r) => ({ ...r, role: pitcherRole(r) }));

  return (
    <div>
      <header className="mb-5">
        <h1 className="text-2xl font-bold">{season} 球季 · {kind === "D" ? "二軍" : ""}投手排行</h1>
        <p className="mt-2 text-sm text-muted">
          {kind === "D" || !isCurrent ? "由逐場/逐年成績彙整（二軍逐打席自 2018 起；救援/中繼僅當季與歷年彙總有）。" : "全名單本季投手。"}
          點欄位標題排序，可依球隊篩選。
        </p>
      </header>

      <LevelYearNav kind={kind} years={years} selectedYear={selectedYear} base="/pitchers" />

      {(() => {
        const teamG = Math.max(0, ...items.map((r) => Number(r.g ?? 0)));
        const qual = Math.round(teamG); // 規定投球局數 ≈ 球隊出賽數 ×1.0
        return <AwardRaces rows={items} cats={AWARD_CATS} qualKey="ip" qualMin={qual}
          note={`規定投球局數約 ${qual}（防禦率/WHIP/K9 套用）。`} />;
      })()}

      <Leaderboard
        rows={rows}
        cols={COLS}
        defaultSort="era"
        defaultDir={1}
        filters={[{ key: "team", label: "球隊" }, { key: "role", label: "角色" }]}
      />
    </div>
  );
}
