import { Card, EmptyState, PlayerLink, RECORD_GRID, RecordCard, SectionHeading, TeamLogo } from "@/components/ui";
import { PregameCard } from "@/components/pregame-card";
import { resolvePregameCard, type PregameResponse } from "@/lib/pregame-card";
import { shortDate } from "@/lib/daily-summary";
import type { CalendarGame, TeamHotZoneResponse } from "@/lib/api";

// 近日焦點的擴充內容：
//   1. 下一場對戰卡／先發預告（UX-TEAM-FOCUS2）——複用既有 <PregameCard/>（不自造平行的
//      勝率元件），整份 pregame response 交給 resolvePregameCard（單一來源守衛，見
//      pregame-single-source.test.ts）；先發未公布時明示「未公布」，不留白也不誤植上一場先發。
//   2. 近期球員熱區（UX-TEAM-HOTZONE1；取代 UX-TEAM-FOCUS2 的 OPS 版本）——擊球品質
//      （打者）＋投球宰制力（投手），過程型口徑，口徑見後端 cpbl.api.team_hotzone
//      docstring（需求方 2026-07-28 定案，不得自行更動）。取代理由不是「跟官方一致」
//      而是指標選擇：12 個打席的 OPS 幾乎是純噪音，過程指標在小樣本下才有訊號。
//
// 「近日焦點」語意＝當季近況，不隨 ?year= 變動（本元件的資料一律來自當季 fetch，
// page.tsx 呼叫時不傳所選年度）。

function NextGameCard({ upcoming, pregame }: {
  upcoming: CalendarGame | undefined;
  pregame: PregameResponse | null;
}) {
  const model = upcoming
    ? resolvePregameCard({
        response: pregame,
        fetchFailed: pregame == null,
        game: { season: upcoming.year, game_sno: upcoming.game_sno, kind_code: upcoming.kind_code },
      })
    : null;

  return (
    <Card padding="p-4">
      <div className="mb-3 flex items-center justify-between border-b border-line pb-2">
        <span className="text-sm font-bold text-ink">下一場</span>
        {upcoming && (
          <span className="text-xs text-faint">
            {shortDate(upcoming.game_date)}{upcoming.venue ? `・${upcoming.venue}` : ""}
          </span>
        )}
      </div>
      {!upcoming ? (
        <EmptyState className="py-3">本季近期無排定賽事。</EmptyState>
      ) : (
        <div className="space-y-3">
          <div className="space-y-1.5">
            <div className="flex items-center gap-2">
              <TeamLogo code={upcoming.away_team_code} name={upcoming.away_team_name} size={22} />
              <span className="text-sm text-ink">{upcoming.away_team_name}</span>
              <span className="ml-auto text-xs text-muted">先發(客) {upcoming.away_starter ?? "未公布"}</span>
            </div>
            <div className="flex items-center gap-2">
              <TeamLogo code={upcoming.home_team_code} name={upcoming.home_team_name} size={22} />
              <span className="text-sm text-ink">{upcoming.home_team_name}</span>
              <span className="ml-auto text-xs text-muted">先發(主) {upcoming.home_starter ?? "未公布"}</span>
            </div>
          </div>
          {model && <PregameCard model={model} homeName={upcoming.home_team_name} />}
        </div>
      )}
    </Card>
  );
}

const f1 = (v: number | null | undefined) => (v == null ? "—" : v.toFixed(1));

function HotBattersList({ data }: { data: TeamHotZoneResponse }) {
  if (data.batters.items.length === 0) return null;
  return (
    <div>
      <SectionHeading caption={`擊球事件（BIP）≥ ${data.batters.min_bip}`}>擊球品質</SectionHeading>
      <ul className={RECORD_GRID}>
        {data.batters.items.map((b) => (
          <RecordCard
            key={b.player_id}
            headline={<><PlayerLink pid={b.player_id} name={b.name} /><span className="text-muted"> 近期擊球品質</span></>}
            detail={`擊球事件 ${b.bip} 次・最高初速 ${f1(b.max_ev)} km/h`}
            anchor={`${f1(b.avg_ev)} km/h`}
          />
        ))}
      </ul>
    </div>
  );
}

function HotPitchersList({ data }: { data: TeamHotZoneResponse }) {
  if (data.pitchers.items.length === 0) return null;
  return (
    <div>
      <SectionHeading caption={`投球數 ≥ ${data.pitchers.min_pitches}`}>投球宰制力</SectionHeading>
      <ul className={RECORD_GRID}>
        {data.pitchers.items.map((p) => (
          <RecordCard
            key={p.player_id}
            headline={<><PlayerLink pid={p.player_id} name={p.name} /><span className="text-muted"> 近期投球宰制力</span></>}
            detail={
              p.avg_ev_against == null
                ? `用球 ${p.pitches} 球・被擊球事件 0 次`
                : `用球 ${p.pitches} 球・被擊球初速 Avg ${f1(p.avg_ev_against)} km/h（${p.bip_against} 次事件）`
            }
            anchor={`揮空率 ${f1(p.whiff_pct)}%`}
          />
        ))}
      </ul>
    </div>
  );
}

function HotZoneCard({ data }: { data: TeamHotZoneResponse }) {
  const allUntracked = data.available && data.coverage != null
    && data.coverage.games_in_window > 0
    && data.coverage.untracked_games === data.coverage.games_in_window;
  const isEmpty = data.batters.items.length === 0 && data.pitchers.items.length === 0;

  return (
    <Card padding="p-4">
      <div className="mb-3 flex items-center justify-between border-b border-line pb-2">
        <span className="text-sm font-bold text-ink">近期球員熱區</span>
        {data.available && data.window && (
          <span className="text-xs text-faint">
            {shortDate(data.window.start)}–{shortDate(data.window.end)}
          </span>
        )}
      </div>
      {!data.available ? (
        <EmptyState className="py-3">本季尚無完賽，暫無熱區資料。</EmptyState>
      ) : allUntracked ? (
        <EmptyState className="py-3">
          窗口內 {data.coverage!.games_in_window} 場比賽皆無逐球追蹤資料（球場端設備覆蓋不全），暫無法排名。
        </EmptyState>
      ) : isEmpty ? (
        <EmptyState className="py-3">窗口內無人達門檻，暫不列榜。</EmptyState>
      ) : (
        <div className="space-y-4">
          {data.coverage != null && data.coverage.untracked_games > 0 && (
            <p className="text-[11px] text-faint">
              窗口內 {data.coverage.games_in_window} 場比賽中有 {data.coverage.untracked_games}{" "}
              場無追蹤資料（球場端設備覆蓋不全），該隊排名可能因此偏低。
            </p>
          )}
          <HotBattersList data={data} />
          <HotPitchersList data={data} />
          <p className="text-[11px] text-faint">
            資料來源：官方逐球追蹤（僅 2026 年起提供，不可跨季比較）。
          </p>
        </div>
      )}
    </Card>
  );
}

export function TeamFocusSection({ upcoming, pregame, hotZone }: {
  upcoming: CalendarGame | undefined;
  pregame: PregameResponse | null;
  hotZone: TeamHotZoneResponse;
}) {
  return (
    <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
      <NextGameCard upcoming={upcoming} pregame={pregame} />
      <HotZoneCard data={hotZone} />
    </div>
  );
}
