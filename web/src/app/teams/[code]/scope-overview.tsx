import { StatTile } from "@/components/ui";
import type { TeamSplitScope } from "@/lib/api";

// 純格式化（與 parts.tsx f2/f3 一致；避免把 server 模組圖拉進 client bundle）。
const f3 = (v: number | null | undefined) => (v == null ? "—" : v.toFixed(3).replace(/^0\./, "."));
const f2 = (v: number | null | undefined) => (v == null ? "—" : v.toFixed(2));
const runDiff = (v: number | null | undefined) => (v == null ? "—" : v > 0 ? `+${v}` : `${v}`);

type ScopeKey = "full" | "first" | "second";
type MetricKey = "ops" | "era" | "whip" | "rs_pg" | "ra_pg" | "run_diff";

/**
 * 攻守概覽（UX-TEAM-SPLIT-SCOPE1）——受控於外層賽季子頁籤（全年/上/下半季）與年度。
 *
 * half 由父層 HierarchicalTabs 的 activeItem 傳入（不自帶切換器）；此元件只渲染所選 half scope。
 * 三範圍走同一 gamelog+games 聚合路徑（/api/v1/season/team-split，禁混用 team_current）；rankOf
 * 依所選範圍在**同範圍** 6 隊內比、不跨範圍。半季小樣本照常顯示並標場數／「樣本偏小」。DER 無半季
 * 粒度且非口徑四指標，切半季固定全年值並去名次、標「· 全年」以免誤導。
 */
export function TeamScopeOverview({ teamCode, scope, teamN, der, half }: {
  teamCode: string;
  scope: TeamSplitScope;
  teamN: number;
  der?: { value: string; rank: number | null } | null;
  half: ScopeKey;
}) {
  const teams = scope.teams;
  const mine = teams.find((t) => t.code === teamCode);

  const rankOf = (key: MetricKey, lowerBetter: boolean): number | null => {
    const v = mine?.[key];
    if (v == null) return null;
    const vals = teams.map((t) => t[key]).filter((x): x is number => x != null);
    const sorted = [...vals].sort((a, b) => (lowerBetter ? a - b : b - a));
    const r = sorted.indexOf(v);
    return r >= 0 ? r + 1 : null;
  };

  const g = mine?.g ?? 0;
  const isHalf = half !== "full";
  const smallSample = isHalf && g > 0 && g < 25;

  return (
    <section className="space-y-3">
      {/* 樣本量標示：小樣本半季照常顯示但標記，避免誤導（需求方定案）。 */}
      <div className="text-[11px] tabular-nums text-muted">
        {g > 0 ? `${g} 場` : "尚無完成場"}
        {smallSample && <span className="ml-1 text-faint">· 樣本偏小</span>}
      </div>
      <div className="grid gap-x-6 gap-y-3 lg:grid-cols-2">
        <div>
          <h3 className="mb-2 text-xs font-semibold tracking-wide text-muted">進攻</h3>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
            <StatTile label="OPS" value={f3(mine?.ops)} accent rank={rankOf("ops", false)} rankTotal={teamN} />
            <StatTile label="得分/場" value={f2(mine?.rs_pg)} rank={rankOf("rs_pg", false)} rankTotal={teamN} />
            <StatTile label="得失分差" value={runDiff(mine?.run_diff)} accent rank={rankOf("run_diff", false)} rankTotal={teamN} />
          </div>
        </div>
        <div>
          <h3 className="mb-2 text-xs font-semibold tracking-wide text-muted">守備投球</h3>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            <StatTile label="ERA" value={f2(mine?.era)} rank={rankOf("era", true)} rankTotal={teamN} />
            <StatTile label="WHIP" value={f2(mine?.whip)} rank={rankOf("whip", true)} rankTotal={teamN} />
            <StatTile label="失分/場" value={f2(mine?.ra_pg)} rank={rankOf("ra_pg", true)} rankTotal={teamN} />
            {/* DER 無半季粒度：切半季固定全年值、去名次、標「· 全年」以免誤導。 */}
            <StatTile label={isHalf ? "DER · 全年" : "DER"} value={der?.value ?? "—"}
              rank={isHalf ? null : (der?.rank ?? null)} rankTotal={teamN} />
          </div>
        </div>
      </div>
    </section>
  );
}
