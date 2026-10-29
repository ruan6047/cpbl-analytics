import Link from "next/link";
import { TeamLogo } from "@/components/ui";
import { teamName3 } from "@/lib/teams";
import type { SeasonClosedChampion, SeasonClosedView } from "@/lib/daily-summary";

// #391 首頁「球季結束」呈現（驗收 1：至少含總冠軍結果與本季回顧入口；其餘交設計，WP3 人工審核）。
// 只在一軍收官（`season_close.major.closed`，後端以 §63／§60 由正式資料推導）時取代左欄的「下一批賽事」空態。
// 視覺沿用既有語彙：surface 卡面＋隊伍印記＋accent 文字連結（UI_UX_SYSTEM §1 原則 3／5；觸控 ≥44px 見 §1 原則 6）。
// ⛔ 不新造路由、不猜二軍冠軍（二軍未收官時那一行不出現）。

function ChampionRow({ label, champion, farm = false }: { label: string; champion: SeasonClosedChampion; farm?: boolean }) {
  const name = `${teamName3(champion.teamCode) || champion.teamCode}${farm ? "二軍" : ""}`;
  return (
    <div data-testid={farm ? "season-closed-farm" : "season-closed-major"} className="flex items-center gap-3">
      <TeamLogo code={champion.teamCode} name={name} size={farm ? 28 : 40} />
      <div className="min-w-0">
        <p className="text-[12.5px] text-muted">{label}</p>
        <p className={`${farm ? "text-base" : "text-xl"} font-bold leading-tight text-ink break-words`}>{name}</p>
        {champion.decidedLabel && (
          champion.decidedHref ? (
            <Link href={champion.decidedHref} className="inline-flex min-h-11 items-center text-[12.5px] text-accent hover:underline">
              {champion.decidedLabel} 封王 →
            </Link>
          ) : <p className="text-[12.5px] text-muted">{champion.decidedLabel} 封王</p>
        )}
      </div>
    </div>
  );
}

export function SeasonClosedCard({ view }: { view: SeasonClosedView }) {
  return (
    <div data-testid="season-closed" className="rounded-md bg-surface px-4 py-4 text-sm text-ink">
      <div className="grid gap-3">
        <ChampionRow label={`${view.season} 台灣大賽總冠軍`} champion={view.major} />
        {view.farm && <ChampionRow label={`${view.season} 二軍總冠軍`} champion={view.farm} farm />}
      </div>
      <nav aria-label="本季回顧" className="mt-3 border-t border-line pt-2">
        <p className="text-[12.5px] text-muted">本季回顧</p>
        <ul className="flex flex-wrap gap-x-4">
          {view.links.map((l) => (
            <li key={l.href}>
              <Link href={l.href} className="inline-flex min-h-11 items-center text-accent hover:underline">{l.label} →</Link>
            </li>
          ))}
        </ul>
      </nav>
    </div>
  );
}
