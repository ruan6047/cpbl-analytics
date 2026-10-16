import type { ReactNode } from "react";

import { Tooltip } from "@/components/tooltip";
import { InfoDot } from "@/components/ui";
import {
  ROSTER_ROLE_TEXT,
  shortDate,
  taipeiTime,
  type PlayoffsWatch,
  type WatchTeam,
} from "@/lib/playoffs-watch";
import { teamShortName } from "@/lib/postseason-journey";
import { PitcherLoadRow, dayLabel } from "./watch-load-strip";

// #289 S08：季後賽第 4 區「觀戰重點」。4A 牛棚近期使用負荷＋官方先發投手狀態。
//
// 紅線：
// - 燈號、完整性與觸發理由全由後端算（`playoffs-watch/v1`），這裡只排字；灰色照後端給的理由呈現，
//   ⛔ 不補成任何等級、⛔ 不寫「可用／待命」。
// - 4B 賽前快照（S09）已停止（#290）：#314 移除兩格占位，⛔ 再放「賽前快照尚未發布」或其他占位框。
// - 官方先發投手：S11 來源定案前每隊一行灰字「未知」（裁定 E1）；⛔ 顯示 074 打序或自行推測。
// - 角色是本站註記，與官方數據分開標示。
// - 4A 呈現（#300 S08c）：燈號＋4 格球數日條＋連投摘要常駐，說明句收進共用 `Tooltip`；見 `watch-load-strip.tsx`。
//   本檔維持 server-safe（⛔ `"use client"`），互動只來自既有 client 島。
// 本元件不建 `/playoffs` 頁、不設錨點；由 S04 頁面掛在 `#watch` 位置。

export function WatchSection({ data }: { data: PlayoffsWatch | null }) {
  return (
    <section aria-labelledby="watch-heading" className="space-y-4">
      <h2 id="watch-heading" className="text-lg font-bold text-ink">觀戰重點</h2>
      {data == null ? (
        <p role="status" className="rounded border border-line bg-surface p-3 text-sm text-muted">
          第 4 區資料暫時無法讀取，其他區不受影響。
        </p>
      ) : data.status !== "ok" ? (
        <p role="status" className="rounded border border-line bg-surface p-3 text-sm text-muted">
          {data.text ?? "目前沒有可呈現的觀戰重點。"}
        </p>
      ) : (
        <>
          <Starters data={data} />
          <Bullpen data={data} />
        </>
      )}
    </section>
  );
}

// —— 官方先發投手 ——————————————————————————————————————————————————

function Starters({ data }: { data: PlayoffsWatch }) {
  return (
    <div className="space-y-3">
      <h3 className="text-base font-bold text-ink">先發對決與看點</h3>
      {data.starters?.length ? (
        <ul className="space-y-1 rounded border border-line bg-surface p-3 text-sm text-faint">
          {data.starters.map((s) => (
            <li key={s.team_code} data-starter-status={s.status}>{teamShortName(s.team_code)}　{s.text}</li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

// —— 4A：牛棚近期使用負荷 ——————————————————————————————————————————————
// #300 S08c：懶人包式呈現。常駐的只有狀態（建議門檻籤、資料更新時間、隊伍缺資料短標）；
// #289 版常駐的說明句收進提示（原話「說明不用直接顯示 頂多是滑鼠移動時提示就好」），
// 再依需求方逐項裁定（6191101762，PLAN-r2 §16）移除零資訊／重複項。

// 區塊 ⓘ：依 §16 裁定只留防誤讀句（E21）與角色註記（E26）；資料範圍（E22）、同步時間（E24，與可見
// 「資料更新」重複）、28 人登錄（E25，恆未知）移除；門檻建議值說明（E23）改掛「建議門檻」籤自己的提示。
function bullpenNote(data: PlayoffsWatch): ReactNode {
  return (
    <div className="space-y-1">
      <p>球數與出賽日的描述，不是健康判斷、可用性或教練調度。</p>
      {data.teams.some((t) => t.roster_status === "submitted") ? (
        <p>預設列名單中 #終結、#勝利組、#長中繼；{ROSTER_ROLE_TEXT}。</p>
      ) : null}
    </div>
  );
}

function Bullpen({ data }: { data: PlayoffsWatch }) {
  const refreshed = taipeiTime(data.as_of.last_refresh_at);
  // 日條比例尺：整個 4A 已知單日球數最大值（⛔ 不用門檻當刻度）。
  const scaleMax = Math.max(0, ...data.teams.flatMap((t) => t.pitchers.flatMap((p) => p.load.days.map((d) => d.pitches))));
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <h3 className="text-base font-bold text-ink">牛棚近期使用負荷</h3>
        <InfoDot label="牛棚負荷說明" content={bullpenNote(data)} />
        {/proposed/.test(data.policy_version) ? (
          <Tooltip suppressUnderline content={<p>門檻為本站建議值（{data.policy_version}，尚未經歷史資料校準）。</p>}>
            <button type="button" data-proposed aria-label="建議門檻：顯示說明"
              className="relative inline-flex min-h-6 touch-manipulation items-center rounded border border-line-strong px-1 text-xs text-muted before:absolute before:-inset-y-2.5 before:inset-x-0 before:content-[''] hover:text-ink">
              建議門檻
            </button>
          </Tooltip>
        ) : null}
        {refreshed ? <span className="text-xs text-muted">資料更新 {refreshed}</span> : null}
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        {data.teams.map((t) => <TeamLoad key={t.team_code} team={t} scaleMax={scaleMax} />)}
      </div>
    </div>
  );
}

function TeamLoad({ team, scaleMax }: { team: WatchTeam; scaleMax: number }) {
  const shown = team.pitchers.filter((p) => p.default_visible);
  const others = team.pitchers.filter((p) => !p.default_visible);
  const gaps = team.days.filter((d) => !d.complete);
  return (
    <div className="min-w-0 rounded border border-line bg-surface p-3">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <h4 className="font-bold text-ink">{teamShortName(team.team_code)}</h4>
        {team.roster_status === "submitted" && gaps.length ? (
          <Tooltip suppressUnderline content={
            <ul className="space-y-0.5">
              {gaps.map((d) => <li key={d.date}>{shortDate(d.date)}（{dayLabel(d.offset)}）：{d.text.join("；")}</li>)}
            </ul>
          }>
            <button type="button" data-team-gaps aria-label="部分日期資料不完整：顯示理由"
              className="relative inline-flex min-h-6 touch-manipulation items-center rounded border border-dashed border-line-strong px-1 text-xs text-muted before:absolute before:-inset-y-2.5 before:inset-x-0 before:content-[''] hover:text-ink">
              部分日期資料不完整
            </button>
          </Tooltip>
        ) : null}
      </div>
      {team.roster_status !== "submitted" ? (
        <p role="status" className="mt-2 text-sm text-muted">{team.roster_text}；不以出賽紀錄代替名單。</p>
      ) : (
        <>
          {shown.length ? (
            <ul className="mt-2 divide-y divide-line">{shown.map((p) => <PitcherLoadRow key={p.player_id} p={p} scaleMax={scaleMax} />)}</ul>
          ) : <p className="mt-2 text-sm text-muted">名單中沒有標記為終結、勝利組或長中繼的投手。</p>}
          {others.length ? (
            <details className="mt-2">
              <summary className="flex min-h-11 cursor-pointer items-center text-sm text-accent">
                其他投手（{others.length}）
              </summary>
              <ul className="divide-y divide-line">{others.map((p) => <PitcherLoadRow key={p.player_id} p={p} scaleMax={scaleMax} />)}</ul>
            </details>
          ) : null}
        </>
      )}
    </div>
  );
}

export default WatchSection;
