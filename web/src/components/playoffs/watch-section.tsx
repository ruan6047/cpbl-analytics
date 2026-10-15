import {
  LEVEL_TEXT,
  LEVEL_TONE,
  ROSTER_ROLE_TEXT,
  STARTER_STATUS_TEXT,
  appearanceText,
  offsetLabel,
  shortDate,
  taipeiTime,
  triggerText,
  type PlayoffsWatch,
  type WatchAnnouncement,
  type WatchPitcher,
  type WatchTeam,
} from "@/lib/playoffs-watch";
import { teamShortName } from "@/lib/postseason-journey";

// #289 S08：季後賽第 4 區「觀戰重點」。4A 牛棚近期使用負荷＋4B 先發對決（S09 前占位）＋原始官方公告事實。
//
// 紅線：
// - 燈號、完整性與觸發理由全由後端算（`playoffs-watch/v1`），這裡只排字；灰色照後端給的理由呈現，
//   ⛔ 不補成任何等級、⛔ 不寫「可用／待命」。
// - 4B 在 S09 啟用前 A、B 兩格各自寫「賽前快照尚未發布」；公告事實另列來源與觀測時間，
//   ⛔ 不套已鎖定 B 樣式。S09 上線後同一位置換成已發布版本（版面不跳）。
// - 角色是本站註記，與官方數據分開標示。
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

// —— 4B：先發對決與看點卡（S09 前占位）＋原始官方公告事實 ——————————————————————

function Starters({ data }: { data: PlayoffsWatch }) {
  return (
    <div className="space-y-3">
      <h3 className="text-base font-bold text-ink">先發對決與看點</h3>
      <div className="grid gap-3 sm:grid-cols-2">
        {data.publication.slots.map((s) => (
          <div key={s.slot} data-slot={s.slot}
            className="rounded border border-dashed border-line-strong bg-surface p-3">
            <p className="text-xs font-bold text-muted">{s.slot === "A" ? "A 推測候選" : "B 官方先發與看點"}</p>
            <p className="mt-1 text-sm text-ink">{s.text}</p>
          </div>
        ))}
      </div>
      {data.announcement ? <Announcement a={data.announcement} /> : null}
    </div>
  );
}

function Announcement({ a }: { a: WatchAnnouncement }) {
  const seen = taipeiTime(a.observed_at);
  return (
    <div className="rounded border border-line bg-surface p-3 text-sm">
      <p className="font-bold text-ink">官方先發打序公告</p>
      <p className="text-xs text-muted">{a.note}</p>
      {a.status === "missing" || a.status === "unavailable" ? (
        <p className="mt-2 text-muted">{a.text}</p>
      ) : (
        <>
          <p className="mt-1 text-xs text-muted">
            來源：{a.source_url ? (
              <a href={a.source_url} className="text-accent underline" rel="noreferrer">官方進階數據站</a>
            ) : "官方進階數據站"}
            {seen ? `・本站觀測 ${seen}（台北）` : ""}
          </p>
          <div className="mt-2 grid gap-3 sm:grid-cols-2">
            {a.teams.map((t) => (
              <div key={t.team_code}>
                <p className="font-bold text-ink">
                  {teamShortName(t.team_code)}：{STARTER_STATUS_TEXT[t.starter_status] ?? t.starter_status}
                </p>
                {t.items.length ? (
                  <ol className="mt-1 space-y-0.5 text-muted">
                    {t.items.map((i) => (
                      <li key={i.player_id}>{i.order}. {i.name ?? i.player_id}（{i.pos}）</li>
                    ))}
                  </ol>
                ) : <p className="text-muted">尚未取得該隊公告。</p>}
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

// —— 4A：牛棚近期使用負荷 ——————————————————————————————————————————————

function Bullpen({ data }: { data: PlayoffsWatch }) {
  const refreshed = taipeiTime(data.as_of.last_refresh_at);
  return (
    <div className="space-y-3">
      <h3 className="text-base font-bold text-ink">牛棚近期使用負荷</h3>
      <p className="text-xs text-muted">
        球數與出賽日的描述，不是健康判斷、可用性或教練調度。{data.scope.note}。
        門檻為本站建議值（{data.policy_version}，尚未經歷史資料校準）。
        {refreshed ? `資料最後同步 ${refreshed}（台北）。` : ""}
      </p>
      <p className="text-xs text-muted">當場 28 人登錄：{data.registration.text}。</p>
      <div className="grid gap-4 lg:grid-cols-2">
        {data.teams.map((t) => <TeamLoad key={t.team_code} team={t} />)}
      </div>
    </div>
  );
}

function TeamLoad({ team }: { team: WatchTeam }) {
  const shown = team.pitchers.filter((p) => p.default_visible);
  const others = team.pitchers.filter((p) => !p.default_visible);
  const gaps = team.days.filter((d) => !d.complete);
  return (
    <div className="min-w-0 rounded border border-line bg-surface p-3">
      <h4 className="font-bold text-ink">{teamShortName(team.team_code)}</h4>
      {team.roster_status !== "submitted" ? (
        <p role="status" className="mt-2 text-sm text-muted">{team.roster_text}；不以出賽紀錄代替名單。</p>
      ) : (
        <>
          <p className="mt-1 text-xs text-muted">預設列名單中 #終結、#勝利組、#長中繼；{ROSTER_ROLE_TEXT}。</p>
          {gaps.length ? (
            <ul className="mt-2 space-y-0.5 text-xs text-muted">
              {gaps.map((d) => <li key={d.date}>{shortDate(d.date)}（{offsetLabel(d.offset)}）：{d.text.join("；")}</li>)}
            </ul>
          ) : null}
          {shown.length ? (
            <ul className="mt-2 divide-y divide-line">{shown.map((p) => <PitcherRow key={p.player_id} p={p} />)}</ul>
          ) : <p className="mt-2 text-sm text-muted">名單中沒有標記為終結、勝利組或長中繼的投手。</p>}
          {others.length ? (
            <details className="mt-2">
              <summary className="flex min-h-11 cursor-pointer items-center text-sm text-accent">
                其他投手（{others.length}）
              </summary>
              <ul className="divide-y divide-line">{others.map((p) => <PitcherRow key={p.player_id} p={p} />)}</ul>
            </details>
          ) : null}
        </>
      )}
    </div>
  );
}

function PitcherRow({ p }: { p: WatchPitcher }) {
  const { load } = p;
  const tone = LEVEL_TONE[load.level];
  const days = [...load.days].sort((a, b) => b.offset - a.offset);
  return (
    <li className="py-2 text-sm" data-level={load.level}>
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <span className="font-bold text-ink">{p.name ?? p.player_id}</span>
        <span className="rounded bg-band px-1.5 text-xs text-muted">
          {p.tactical_role && p.tactical_role !== "unclassified" ? `#${p.tactical_role}` : "角色未標記"}
        </span>
        <span className={`inline-flex items-center gap-1 font-bold ${tone.text}`}>
          <span aria-hidden className={`inline-block h-2.5 w-2.5 rounded-full ${tone.dot}`} />
          {LEVEL_TEXT[load.level]}
        </span>
        {load.live ? <span className="rounded border border-accent px-1 text-xs text-accent">即時</span> : null}
      </div>
      {load.triggers.length ? (
        <p className="mt-0.5 text-xs text-ink">{load.triggers.map(triggerText).join("、")}</p>
      ) : null}
      {load.level === "unknown" && load.incomplete.length ? (
        <p className="mt-0.5 text-xs text-muted">
          資料不完整：{load.incomplete.map((i) => `${shortDate(i.date)} ${i.text.join("、")}`).join("；")}
        </p>
      ) : null}
      <dl className="mt-1 grid grid-cols-[auto_1fr] gap-x-2 gap-y-0.5 text-xs text-muted">
        <dt>近期球數</dt>
        <dd className="text-ink">
          {days.map((d) => `${shortDate(d.date)} ${d.complete ? d.pitches : `${d.pitches}+?`}`).join("・")}
          {load.unattributed.length ? `（另有保留賽 ${load.unattributed.map((u) => u.pitches ?? "?").join("、")} 球日期未定）` : ""}
        </dd>
        <dt>完整休息</dt>
        <dd className="text-ink">
          {load.full_rest_days != null ? `${load.full_rest_days} 天（最後投球 ${shortDate(load.last_pitch_date)}）`
            : load.rest_unknown_reason ? "無法判定（近期資料不完整）" : "本季無投球紀錄"}
        </dd>
        <dt>連續登板</dt>
        <dd className="text-ink">
          {load.metrics.C == null ? "無法判定" : `${load.metrics.C}${load.c_at_least ? "+" : ""} 日`}
          ・今日已登板 {load.metrics.Q ?? "?"} 次
        </dd>
        <dt>最近登板</dt>
        <dd className="text-ink">{p.recent.length ? p.recent.map(appearanceText).join("；") : "本季無登板紀錄"}</dd>
        {p.consecutive_era ? (
          <>
            <dt>連投時成績</dt>
            <dd className="text-ink">
              {p.consecutive_era.appearances} 場 {p.consecutive_era.ip ?? "?"} 局 自責 {p.consecutive_era.er ?? "?"}・
              ERA {p.consecutive_era.era == null ? "不可定義" : p.consecutive_era.era.toFixed(2)}
              <span className="block text-muted">{p.consecutive_era.scope}；不代表連投導致此成績</span>
            </dd>
          </>
        ) : null}
        <dt>當場登錄</dt>
        <dd>{p.registration.text}</dd>
      </dl>
    </li>
  );
}

export default WatchSection;
