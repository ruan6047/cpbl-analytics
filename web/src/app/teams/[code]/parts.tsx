// 球隊頁展示元件與常數（Server Component 可用；無 client hooks）。
import Link from "next/link";
import { ActivePill, Card, EmptyState, ENTITY_LINK, ENTITY_LINK_TEXT } from "@/components/ui";
import { DataTable, type Column } from "@/components/table";
import type { SpecialRecord, WL, WTL, api } from "@/lib/api";

type TeamPlayersData = Awaited<ReturnType<typeof api.teamPlayers>>;
type Coach = NonNullable<TeamPlayersData["coaches"]>[number];
type Manager = NonNullable<TeamPlayersData["managers"]>[number];
type RetiredNumber = NonNullable<TeamPlayersData["retired"]>[number];

export const f3 = (v: number | null | undefined) => (v == null ? "—" : v.toFixed(3).replace(/^0\./, "."));
export const f2 = (v: number | null | undefined) => (v == null ? "—" : v.toFixed(2));

// W-L 上色字串
function wl(p?: WL) {
  if (!p) return <span className="text-faint">—</span>;
  const [w, l] = p;
  if (w + l === 0) return <span className="text-faint">0-0</span>;
  const c = w / (w + l);
  return <span className={c > 0.5 ? "text-up" : c < 0.5 ? "text-down" : "text-muted"}>{w}-{l}</span>;
}
function wtl(p?: WTL) {
  if (!p) return <span className="text-faint">—</span>;
  const [w, t, l] = p;
  if (w + t + l === 0) return <span className="text-faint">—</span>;
  return <span className={w > l ? "text-up" : l > w ? "text-down" : "text-muted"}>{w}-{t}-{l}</span>;
}

// 特殊戰績分組（單隊縱向呈現）
export const GROUPS: { title: string; rows: { label: string; render: (s: SpecialRecord) => React.ReactNode }[] }[] = [
  {
    title: "場地",
    rows: [
      { label: "天然草皮", render: (s) => wl(s.natural) },
      { label: "人工草皮", render: (s) => wl(s.artificial) },
      { label: "室內（大巨蛋）", render: (s) => wl(s.indoor) },
    ],
  },
  {
    title: "比分型",
    rows: [
      { label: "一分差", render: (s) => wl(s.one_run) },
      { label: "大勝大敗（≥5）", render: (s) => wl(s.blowout) },
      { label: "完封 勝-被", render: (s) => wl(s.shutout) },
      { label: "逆轉 勝-被", render: (s) => wl(s.comeback) },
    ],
  },
  {
    title: "賽況軌跡",
    rows: [
      { label: "得分先馳", render: (s) => wl(s.scored_first) },
      { label: "先失分", render: (s) => wl(s.scored_first_against) },
      { label: "戰況激烈", render: (s) => wl(s.intense) },
      { label: "順風（曾領先≥3）", render: (s) => wl(s.tailwind) },
      { label: "逆風（曾落後≥3）", render: (s) => wl(s.headwind) },
      { label: "大局（單局≥4）", render: (s) => wl(s.big_inning) },
    ],
  },
  {
    title: "終局與守備",
    rows: [
      { label: "延長賽", render: (s) => wl(s.extra) },
      { label: "救援守成 成-敗", render: (s) => wl(s.save) },
      { label: "失誤場", render: (s) => wl(s.errorful) },
    ],
  },
  {
    title: "賽程 / 對手",
    rows: [
      { label: "平日", render: (s) => wl(s.weekday) },
      { label: "假日", render: (s) => wl(s.weekend) },
      { label: "vs 左投", render: (s) => wl(s.vs_lhp) },
      { label: "vs 右投", render: (s) => wl(s.vs_rhp) },
    ],
  },
  {
    title: "系列賽",
    rows: [
      { label: "三連戰 勝-平-負", render: (s) => wtl(s.series3) },
      { label: "三連戰橫掃", render: (s) => <span className="text-muted">{s.sweeps || "—"}</span> },
      { label: "被三連戰橫掃", render: (s) => <span className="text-muted">{s.swept || "—"}</span> },
      { label: "雙連賽 勝-平-負", render: (s) => wtl(s.series2) },
    ],
  },
  {
    title: "再見 / 連勝",
    rows: [
      { label: "再見勝", render: (s) => <span className="text-up">{s.walkoff || "—"}</span> },
      { label: "被再見", render: (s) => <span className="text-down">{s.walked_off || "—"}</span> },
      { label: "最大連勝", render: (s) => <span className="text-up">{s.max_win_streak || "—"}</span> },
      { label: "最大連敗", render: (s) => <span className="text-down">{s.max_lose_streak || "—"}</span> },
    ],
  },
];

// 現役教練團（僅現役球團；官網現役名單，無歷史勝率）
export function CoachGrid({ coaches, color }: { coaches: Coach[]; color: string }) {
  if (coaches.length === 0) return null;
  return (
    <section>
      <h2 className="mb-1 text-lg font-semibold">現役教練團</h2>
      <p className="mb-3 text-[11px] text-faint">官方現役教練名單（一軍）；總教練居首。</p>
      <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-3 lg:grid-cols-4">
        {coaches.map((co) => (
          <Card key={`${co.pos}-${co.name}`} className="flex items-center gap-2.5 p-3">
            <span className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-md font-mono text-xs font-bold tabular-nums"
              style={{ background: `${color}1a`, color }}>{co.uniform_no ?? "—"}</span>
            <div className="min-w-0">
              <div className="truncate text-[11px] text-muted">{co.pos.replace(/^一軍/, "")}</div>
              {co.player_id ? (
                <Link href={`/players/${co.player_id}`} className={`truncate block font-medium ${ENTITY_LINK}`} title="前球員 · 看球員頁">
                  {co.name}
                </Link>
              ) : (
                <Link href={`/people/coach/${encodeURIComponent(co.name)}`} className={`truncate block font-medium ${ENTITY_LINK}`} title="純教練 · 看經歷頁">
                  {co.name}
                </Link>
              )}
            </div>
          </Card>
        ))}
      </div>
    </section>
  );
}

// 歷任總教練（維基百科；可能需人工複查）
export function ManagersTable({ managers }: { managers: Manager[] }) {
  if (managers.length === 0) return null;
  return (
    <section>
      <h2 className="mb-1 text-lg font-semibold">歷任總教練</h2>
      <p className="mb-3 text-[11px] text-faint">名單來源：中文維基百科各球隊條目；前球員姓名可點入球員頁。<span className="text-accent">勝-和-敗</span>於該年無換帥／代理時以本站逐場一軍資料重算（維基數據常滯後當季）；有中途換帥的年度沿用維基拆分。部分球隊維基無此表故未列。</p>
      <DataTable
        columns={[
          { header: "總教練", cell: (m) => <>{m.player_id ? <Link href={`/players/${m.player_id}`} className={ENTITY_LINK}>{m.name}</Link> : m.name}{m.era && <span className="ml-1.5 text-[10px] text-faint">{m.era}</span>}</>, nowrap: true, className: "font-sans" },
          { header: "任期", cell: (m) => (m.from === m.to ? m.from : `${m.from}–${m.to}`), nowrap: true, className: "text-muted" },
          { header: "勝-和-敗", cell: (m) => <span title={m.source === "db" ? "本站逐場一軍資料重算" : "維基百科數據"}>{m.w}-{m.t}-{m.l}{m.source === "db" && <span className="ml-1 text-[9px] text-up align-top">●</span>}</span>, nowrap: true },
          { header: "勝率", cell: (m) => (m.win_pct == null ? "—" : m.win_pct.toFixed(3).replace(/^0\./, ".")), className: "text-accent" },
          { header: "季後賽", cell: (m) => m.postseason || "—", className: "text-muted" },
          { header: "總冠軍", cell: (m) => (m.championships ? <span className="text-up">{m.championships}</span> : "—") },
        ] satisfies Column<(typeof managers)[number]>[]}
        rows={managers}
        rowKey={(m, i) => `${m.name}-${m.from}-${i}`}
        dense
      />
    </section>
  );
}

// 退休背號（維基；球迷／球團不附球員連結，已恢復使用標示）
export function RetiredNumbers({ retired, color }: { retired: RetiredNumber[]; color: string }) {
  if (retired.length === 0) return null;
  return (
    <section>
      <h2 className="mb-1 text-lg font-semibold">退休背號</h2>
      <p className="mb-3 text-[11px] text-faint">資料來源：中文維基百科各球隊條目；球迷／球團背號不附球員。已恢復使用者淡化標示。</p>
      <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-3 lg:grid-cols-4">
        {retired.map((r) => {
          const revoked = r.status === "revoked";
          const sub = r.holder_type === "fans" ? "球迷專屬" : r.holder_type === "org" ? "球團"
            : revoked ? "已恢復使用" : "永久退休";
          const inner = (
            <Card className={`flex items-center gap-3 p-3 ${revoked ? "opacity-55" : ""}`}>
              <span className="grid h-11 w-11 shrink-0 place-items-center rounded-lg font-mono text-xl font-bold tabular-nums"
                style={{ background: `${color}1a`, color }}>{r.number}</span>
              <div className="min-w-0">
                {/* 整張卡維持可點（外層 <Link> 不動），底線只套在球員名文字。
                    原本連結態用 text-accent，正是 §3.5 明文禁止的實體名紅字；改走 ENTITY_LINK。
                    line-through 留在外層 div：CSS text-decoration 會往內層傳遞並疊加，
                    避免與內層 underline 在同一個 text-decoration-line 上互相覆蓋。 */}
                <div className={`truncate font-medium ${revoked ? "line-through" : ""}`}>
                  {r.player_id
                    ? <span className={ENTITY_LINK_TEXT}>{r.holder}</span>
                    : <span className="text-ink">{r.holder}</span>}
                </div>
                <div className="text-[10px] text-faint">{sub}</div>
              </div>
            </Card>
          );
          return r.player_id
            ? <Link key={r.number} href={`/players/${r.player_id}`} className="group" title={r.note ?? "前球員 · 看球員頁"}>{inner}</Link>
            : <div key={r.number} title={r.note ?? undefined}>{inner}</div>;
        })}
      </div>
    </section>
  );
}

export function RosterChips({ label, players, color, dim }: {
  label: string; players: { player_id: string; name: string }[]; color: string; dim?: boolean;
}) {
  if (players.length === 0) return null;
  return (
    <div>
      {label && <div className="mb-1.5 text-xs font-medium text-muted">{label}</div>}
      <div className="flex flex-wrap gap-1.5">
        {players.map((p) => (
          // 整顆 chip 維持可點（外層 <Link> 不動），ENTITY_LINK 視覺只套姓名文字。
          // ⚠️ Design Gate 待裁定：ENTITY_LINK 含 `text-ink`，會覆蓋 chip 原本的隊色文字
          //（隊色仍保留在 chip 邊框，因 hover:border-current 取 <Link> 的 currentColor）。
          // 若需求方認為隊色文字才是此處的識別重點，把 style 移到內層 span 即可還原。
          <Link key={p.player_id} href={`/players/${p.player_id}`}
            className={`group rounded-full border border-line px-2.5 py-1 text-sm transition hover:border-current ${dim ? "text-muted" : ""}`}
            style={dim ? undefined : { color }}>
            <span className={ENTITY_LINK_TEXT}>{p.name}</span>
          </Link>
        ))}
      </div>
    </div>
  );
}

export function RosterTable({ rows, cols }: {
  rows: { id: string; name: string; active: boolean; span: string; a: string; b: string }[];
  cols: string[];
}) {
  if (rows.length === 0) return <EmptyState>尚無資料。</EmptyState>;
  return (
    <DataTable
      columns={[
        // 底線只跟著球員名（pill 不套），但整塊含 pill 維持可點——外層 <Link> 不動。
        {
          header: cols[0],
          cell: (r) => (
            <Link href={`/players/${r.id}`} className="group inline-flex items-center gap-1.5">
              <span className={ENTITY_LINK_TEXT}>{r.name}</span>
              {r.active && <ActivePill />}
            </Link>
          ),
          className: "font-sans",
        },
        { header: cols[1], cell: (r) => r.span, className: "font-mono text-[11px] text-muted" },
        { header: cols[2], cell: (r) => r.a, className: "font-mono" },
        { header: cols[3], cell: (r) => r.b, className: "font-mono text-muted" },
      ] satisfies Column<(typeof rows)[number]>[]}
      rows={rows}
      rowKey={(r) => r.id}
      dense
      bodyClassName="tabular-nums"
    />
  );
}

export function PlayerTable({ rows, cols }: { rows: { id: string; name: string | null; a: string; b: string }[]; cols: [string, string, string] | string[] }) {
  if (rows.length === 0) return <EmptyState>尚無資料。</EmptyState>;
  return (
    <DataTable
      columns={[
        { header: cols[0], cell: (r) => <Link href={`/players/${r.id}`} className={ENTITY_LINK}>{r.name ?? "—"}</Link>, className: "font-sans" },
        { header: cols[1], cell: (r) => r.a, className: "font-mono" },
        { header: cols[2], cell: (r) => r.b, className: "font-mono text-muted" },
      ] satisfies Column<(typeof rows)[number]>[]}
      rows={rows}
      rowKey={(r) => r.id}
      dense
      bodyClassName="tabular-nums"
    />
  );
}
