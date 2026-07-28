import type { ReactNode } from "react";
import { Card, EmptyState, PlayerLink, RECORD_GRID, RecordCard, SectionHeading, StatusBadge, TeamLogo } from "@/components/ui";
import { PregameCard } from "@/components/pregame-card";
import { Tooltip } from "@/components/tooltip";
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
//
// 2026-07-28 需求方追加需求「桌機要能不用捲軸」（1440×1080）：原本「下一場＋熱區」
// 一列兩欄、「即將挑戰的紀錄」另起整幅一列，桌機下「下一場」（矮）那一欄下方會空出
// ~255px（被熱區那一欄的高度撐開又沒東西填）。改成「下一場＋即將挑戰的紀錄」疊在
// 左欄、熱區獨占右欄——原本浪費的空白被左欄下半段的紀錄卡填滿，不是靠刪內容擠出
// 空間。`records` 由 page.tsx 傳入（保持 TeamFocusSection 不需認識 TeamRecordsSection
// 的資料型別，關注點分離）。

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

// 2026-07-28 需求方人工審核第一輪退回（桌機 lg:grid-cols-3 每卡實得寬度窄，中文
// 逐字斷行）：headline 不再附加「近期擊球品質／投球宰制力」——每卡都在同一個
// SectionHeading 底下、整段文字對本行不帶資訊，卻在最窄的欄位裡跟數字搶空間；
// anchor 不再附加指標名（「揮空率」）——整個區段排序鍵只有一種，指標名改上移到
// 卡片標題的 INFO tooltip 統一講一次（見下方 HOT_ZONE_INFO）。headline 只留
// 球員名＋detail 帶樣本數，anchor 只留「數值＋單位」：不動口徑/門檻/數字本身，
// 純粹是 RecordCard（UX-TEAM-RECORDS1 共用元件，其 anchor 是為「還差 1」
// 「隊史新高」這種四字內短錨點設計）在長錨點下的寬度預算問題，解法是縮短文字
// 而非改元件版面——動 RecordCard 的版面會牽動已定案上線的 RECORDS1，改文字不會。
//
// 2026-07-28 需求方追加：桌機收斂到 1440×1080 不用捲軸還差一截，指定兩種處理
// （沿用既有 pattern，不自造）：
//   1. 三行判準/來源說明收進標題後的 INFO 按鈕——沿用 ability-card.tsx 雷達圖
//      右上角 `?` 的 pattern（Tooltip 包按鈕，interactive，內容可分段），三段
//      合併成一顆問號而非各自一顆。
//   2. 每張卡的次要數據（最高初速／被擊球初速 Avg）改 hover／點按才出現。
//      **卡面紅線 4「樣本數必須同列顯示」不可退讓**——擊球事件數／用球數這個
//      「這個數字代表幾次樣本」的限定條件永遠可見，只有次要數值進 tooltip。
//      行動裝置沒有 hover：<768px 直接把 extra 文字常駐顯示（單欄有空間），
//      ≥768px 才換成 tooltip 觸發鈕，兩者互斥用 `md:hidden`／`hidden md:*`
//      切換，純 CSS 斷點、無 JS 偵測視窗寬度（避免 hydration 不一致）。
function CardDetail({ name, sample, extra }: { name: string; sample: string; extra: ReactNode }) {
  return (
    <div className="mt-0.5 flex items-center gap-1 text-xs text-faint">
      <span>{sample}</span>
      <span className="md:hidden">・{extra}</span>
      <Tooltip content={extra} suppressUnderline interactive>
        {/* 觸控熱區目標同 ContextSwitcher 的原則（視覺圖示不放大、熱區另外撐開），
            但**技術手法不同**：ContextSwitcher 是獨立工具列，用 min-h-11 撐按鈕
            本體沒有副作用；這裡的圖示是每列密排的卡片明細行內聯元素，按鈕本體若
            真的撐到 44px 會把 flex 列高一起拉到 44px（六張卡等於白白多出
            ~180px，剛壓下去的 1440×1080 版面又會爆）。改用 `relative` +
            `::before` 負 inset 疊一塊不佔版位（`position:absolute` 脫離文件流，
            不影響父層列高）但可點擊的透明熱區，補到 WCAG 2.5.8 的 24px 下限
            （14px 圖示每邊補 5px）。aria-label 帶球員名（非泛用「更多數據」）——
            每張卡代表不同球員，敘述需帶對象才有意義（需求方 2026-07-28 明訂）。
            圖示字級 text-[10px]（非 text-[9px]）：UI_UX_SYSTEM §2.3 明訂
            sub-9px 低於可讀下限，10px 對應既有 `micro` 角色（尚未 token 化但
            允許沿用，見同節）。 */}
        <button type="button" aria-label={`${name} 詳細數據`}
          className="relative hidden h-3.5 w-3.5 shrink-0 touch-manipulation place-items-center rounded-full border border-line text-[10px] font-semibold leading-none text-muted before:absolute before:-inset-[5px] before:content-[''] hover:text-ink md:grid">
          i
        </button>
      </Tooltip>
    </div>
  );
}

function HotBattersList({ data }: { data: TeamHotZoneResponse }) {
  if (data.batters.items.length === 0) return null;
  return (
    <div>
      <SectionHeading>擊球品質</SectionHeading>
      <ul className={RECORD_GRID}>
        {data.batters.items.map((b) => (
          <RecordCard
            key={b.player_id}
            headline={<PlayerLink pid={b.player_id} name={b.name} />}
            detail={<CardDetail name={b.name} sample={`擊球事件 ${b.bip} 次`} extra={`最高初速 ${f1(b.max_ev)} km/h`} />}
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
      <SectionHeading>投球宰制力</SectionHeading>
      <ul className={RECORD_GRID}>
        {data.pitchers.items.map((p) => (
          <RecordCard
            key={p.player_id}
            headline={<PlayerLink pid={p.player_id} name={p.name} />}
            detail={
              <CardDetail
                name={p.name}
                sample={`用球 ${p.pitches} 球`}
                extra={p.avg_ev_against == null
                  ? "被擊球事件 0 次"
                  : `被擊球初速 Avg ${f1(p.avg_ev_against)} km/h（${p.bip_against} 次事件）`}
              />
            }
            anchor={`${f1(p.whiff_pct)}%`}
          />
        ))}
      </ul>
    </div>
  );
}

// 標題 INFO：兩區段判準＋（有缺口才附）覆蓋缺口成因＋資料來源，合併一顆問號。
// 覆蓋缺口的「數字」本身（幾場無追蹤）不在這裡——那是紅線 1 要求常駐可見的
// 揭露，留在標題列的 StatusBadge chip；這裡只放「為什麼」（球場端設備覆蓋不全）
// 這個解釋性文字，不是被排名數字的限定條件，適合收進 hover。
function HotZoneInfo({ data }: { data: TeamHotZoneResponse }) {
  return (
    <div className="space-y-2">
      <div>
        <div className="font-semibold">擊球品質判準</div>
        <div>擊球事件（BIP）≥ {data.batters.min_bip}・排序＝平均擊球初速</div>
      </div>
      <div>
        <div className="font-semibold">投球宰制力判準</div>
        <div>投球數 ≥ {data.pitchers.min_pitches}・排序＝揮空率</div>
      </div>
      {data.coverage != null && data.coverage.untracked_games > 0 && (
        <div>球場端設備覆蓋不全，無追蹤資料的比賽不計入該隊選手樣本，該隊排名可能因此偏低。</div>
      )}
      <div className="text-paper/70">資料來源：官方逐球追蹤（僅 2026 年起提供，不可跨季比較）。</div>
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
        <span className="flex items-center gap-1.5">
          <span className="text-sm font-bold text-ink">近期球員熱區</span>
          {data.available && (
            <Tooltip content={<HotZoneInfo data={data} />} suppressUnderline interactive>
              {/* 18px 圖示（h-4.5 w-4.5）低於 WCAG 2.5.8 的 24px 觸控目標下限（需求方
                  2026-07-28 375px 實測發現）。同 CardDetail 的「i」按鈕：視覺不放大，
                  用 `relative` + `::before` 負 inset 補到 24px（每邊 +3px），
                  不用 ContextSwitcher 的 min-h-11 真實撐大——這裡也在 mb-3 的標題列
                  裡跟其他文字同列，真的撐到 44px 一樣會拉高整條標題列。 */}
              <button type="button" aria-label="近期球員熱區判準與資料來源說明"
                className="relative grid h-4.5 w-4.5 place-items-center rounded-full border border-line bg-surface text-[10px] font-semibold leading-none text-muted before:absolute before:-inset-[3px] before:content-[''] hover:text-ink">
                ?
              </button>
            </Tooltip>
          )}
        </span>
        <span className="flex items-center gap-2">
          {/* 紅線 1：覆蓋缺口的「數字」必須常駐可見，不得整條藏進 hover——
              只有「為什麼」的說明文字收進上面的 INFO。 */}
          {data.coverage != null && data.coverage.untracked_games > 0 && (
            <StatusBadge tone="warn">{data.coverage.untracked_games}/{data.coverage.games_in_window} 場無追蹤</StatusBadge>
          )}
          {data.available && data.window && (
            <span className="text-xs text-faint">
              {shortDate(data.window.start)}–{shortDate(data.window.end)}
            </span>
          )}
        </span>
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
        <div className="space-y-3">
          <HotBattersList data={data} />
          <HotPitchersList data={data} />
        </div>
      )}
    </Card>
  );
}

export function TeamFocusSection({ upcoming, pregame, hotZone, records, recentGames }: {
  upcoming: CalendarGame | undefined;
  pregame: PregameResponse | null;
  hotZone: TeamHotZoneResponse;
  records: ReactNode;
  recentGames: ReactNode;
}) {
  // items-start：兩段式熱區（打者＋投手）比 FOCUS2 單段熱區高很多，預設 grid 拉伸
  // 會把左欄撐到跟右欄同高。改各欄依自身內容收高，兩欄不再被迫等高。
  //
  // 左欄「下一場＋即將挑戰的紀錄」疊放、右欄「熱區＋近期賽事」疊放——不是
  // 「一列兩欄＋下方整幅」（桌機不用捲軸需求，見檔案頂端說明）。近期賽事塞進
  // 右欄是因為熱區改 INFO/hover 收斂後右欄還有大量餘裕（實測右欄 252px vs
  // 左欄 562px），移進來完全落在既有餘裕內。
  return (
    <div className="grid grid-cols-1 items-start gap-3 md:grid-cols-2">
      <div className="space-y-3">
        <NextGameCard upcoming={upcoming} pregame={pregame} />
        {records}
      </div>
      <div className="space-y-3">
        <HotZoneCard data={hotZone} />
        {recentGames}
      </div>
    </div>
  );
}
