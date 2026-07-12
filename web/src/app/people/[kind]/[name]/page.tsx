"use client";

// 個人頁（UX-7C，Person Hub 甲案雙軌）：無 acnt 身分（純教練/裁判）。
// 有 acnt 的人走 /players/[id]（canonical）；教練若名字唯一對應球員，附「球員時期 →」連結。
// 裁判記分卡為推算（TrackMan 固定規則帶），樣本誠實：一律帶追蹤場數。
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { clientGet } from "@/lib/client";
import { Card, EmptyState, Eyebrow, StatTile, TeamLogo } from "@/components/ui";
import { DataTable, type Column } from "@/components/table";

type CoachData = {
  name: string;
  roles: { year: number; team_code: string; team_name: string | null; pos: string; uniform_no: string | null }[];
  manager_eras: { team_code: string; team_name: string | null; era_name: string; from_year: number; to_year: number;
    g: number; w: number; l: number; ties: number; win_pct: number | null; postseason: number; championships: number }[];
  player_id: string | null;
  player_ambiguous: boolean;
};
type UmpData = {
  name: string; season: number;
  positions: { head: number; first: number; second: number; third: number; lines: number };
  scorecard: { tracked_games: number; called: number; acc: number | null; strike_acc: number | null; ball_acc: number | null };
  recent_games: { game_sno: number; game_date: string; venue: string | null;
    away_team_name: string; away_team_code: string; away_score: number;
    home_team_name: string; home_team_code: string; home_score: number; called: number }[];
};

function CoachView({ d }: { d: CoachData }) {
  const cur = d.roles[0];
  const cols: Column<CoachData["roles"][number]>[] = [
    { header: "年度", cell: (r) => String(r.year), align: "right" },
    { header: "球隊", cell: (r) => <span className="flex items-center gap-1.5 font-sans"><TeamLogo code={r.team_code} name={r.team_name} size={16} />{r.team_name ?? r.team_code}</span>, nowrap: true },
    { header: "職務", cell: (r) => r.pos, nowrap: true, className: "font-sans text-ink" },
    { header: "背號", cell: (r) => r.uniform_no ?? "—", align: "right" },
  ];
  const mcols: Column<CoachData["manager_eras"][number]>[] = [
    { header: "球隊", cell: (r) => <span className="flex items-center gap-1.5 font-sans"><TeamLogo code={r.team_code} name={r.team_name} size={16} />{r.team_name ?? r.team_code}</span>, nowrap: true },
    { header: "任期", cell: (r) => (r.from_year === r.to_year ? String(r.from_year) : `${r.from_year}–${r.to_year}`), nowrap: true },
    { header: "場次", cell: (r) => String(r.g), align: "right" },
    { header: "戰績", cell: (r) => `${r.w}-${r.ties}-${r.l}`, align: "right", nowrap: true },
    { header: "勝率", cell: (r) => (r.win_pct != null ? Number(r.win_pct).toFixed(3).replace(/^0/, "") : "—"), align: "right" },
    { header: "季後賽", cell: (r) => String(r.postseason), align: "right" },
    { header: "冠軍", cell: (r) => (r.championships ? `🏆×${r.championships}` : "—"), align: "right" },
  ];
  return (
    <div>
      <header className="mb-6">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-extrabold tracking-tight text-ink">{d.name}</h1>
          {cur && (
            <span className="flex items-center gap-1.5 rounded-full bg-surface-2 px-2.5 py-1 text-xs font-semibold text-muted">
              <TeamLogo code={cur.team_code} name={cur.team_name} size={15} decorative />{cur.year} {cur.pos}
            </span>
          )}
          {d.player_id && (
            <Link href={`/players/${d.player_id}`} className="text-xs text-accent hover:underline">球員時期資料 →</Link>
          )}
        </div>
        {d.player_ambiguous && (
          <p className="mt-1.5 text-xs text-faint">（有多位同名球員，暫不歸戶球員資料）</p>
        )}
      </header>
      {d.manager_eras.length > 0 && (
        <section className="mb-8">
          <Eyebrow className="mb-3">總教練戰績</Eyebrow>
          <DataTable columns={mcols} rows={d.manager_eras} rowKey={(r, i) => `${r.team_code}-${i}`} dense />
        </section>
      )}
      <section className="mb-8">
        <Eyebrow className="mb-3">教練職務</Eyebrow>
        <DataTable columns={cols} rows={d.roles} rowKey={(r, i) => `${r.year}-${r.team_code}-${i}`} dense
          emptyText="無教練職務紀錄" />
      </section>
    </div>
  );
}

function UmpireView({ d }: { d: UmpData }) {
  const sc = d.scorecard;
  const tracked = Number(sc.tracked_games) || 0;
  const pos: [string, number][] = [
    ["主審", d.positions.head], ["一壘", d.positions.first], ["二壘", d.positions.second],
    ["三壘", d.positions.third], ["外線", d.positions.lines],
  ];
  const gcols: Column<UmpData["recent_games"][number]>[] = [
    { header: "日期", cell: (r) => r.game_date, nowrap: true },
    {
      header: "對戰", nowrap: true, className: "font-sans",
      cell: (r) => (
        <span className="flex items-center gap-1.5">
          <TeamLogo code={r.away_team_code} name={r.away_team_name} size={15} />
          <span className="font-mono tabular-nums">{r.away_score}:{r.home_score}</span>
          <TeamLogo code={r.home_team_code} name={r.home_team_name} size={15} />
          <span className="text-xs text-faint">{r.venue ?? ""}</span>
        </span>
      ),
    },
    {
      header: "記分卡", align: "right",
      cell: (r) => (r.called > 0
        ? <Link href={`/games/${r.game_sno}`} className="text-accent hover:underline">看單場 →</Link>
        : <span className="text-faint">無追蹤</span>),
    },
  ];
  return (
    <div>
      <header className="mb-6">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-extrabold tracking-tight text-ink">{d.name}</h1>
          <span className="rounded-full bg-surface-2 px-2.5 py-1 text-xs font-semibold text-muted">裁判 · {d.season} 球季</span>
        </div>
        <p className="mt-1.5 text-sm text-muted">好壞球判決為推算（TrackMan 固定規則帶），僅涵蓋有設備場次。</p>
      </header>
      <section className="mb-8 grid gap-4 lg:grid-cols-2">
        <Card>
          <Eyebrow className="mb-3">執法場次（{d.season}）</Eyebrow>
          <div className="grid grid-cols-5 gap-2">
            {pos.map(([l, v]) => <StatTile key={l} label={l} value={String(v)} />)}
          </div>
        </Card>
        <Card>
          <Eyebrow className="mb-3">主審記分卡 <span className="font-normal normal-case text-faint">（{tracked} 場追蹤 · {sc.called} 球）</span></Eyebrow>
          {tracked > 0 ? (
            <>
              <div className="grid grid-cols-3 gap-2">
                <StatTile label="判決準確率" value={sc.acc != null ? `${sc.acc}%` : "—"} accent />
                <StatTile label="帶內判好球" value={sc.strike_acc != null ? `${sc.strike_acc}%` : "—"} />
                <StatTile label="帶外判壞球" value={sc.ball_acc != null ? `${sc.ball_acc}%` : "—"} />
              </div>
              {tracked < 5 && <p className="mt-2 text-[11px] text-faint">樣本僅 {tracked} 場，指標僅供參考。</p>}
            </>
          ) : (
            <EmptyState>本季無 TrackMan 追蹤場次，無記分卡。</EmptyState>
          )}
        </Card>
      </section>
      <section className="mb-8">
        <Eyebrow className="mb-3">近期主審場次</Eyebrow>
        <DataTable columns={gcols} rows={d.recent_games} rowKey={(r) => r.game_sno} dense
          emptyText="本季無主審場次" />
      </section>
    </div>
  );
}

export default function PersonPage() {
  const { kind, name } = useParams<{ kind: string; name: string }>();
  const decoded = decodeURIComponent(name);
  const [coach, setCoach] = useState<CoachData | null>(null);
  const [ump, setUmp] = useState<UmpData | null>(null);
  const [err, setErr] = useState(false);

  useEffect(() => {
    setCoach(null); setUmp(null); setErr(false);
    if (kind === "coach") {
      clientGet<CoachData>(`/api/v1/people/coach/${encodeURIComponent(decoded)}`)
        .then(setCoach).catch(() => setErr(true));
    } else if (kind === "umpire") {
      clientGet<UmpData>(`/api/v1/people/umpire/${encodeURIComponent(decoded)}`)
        .then(setUmp).catch(() => setErr(true));
    } else {
      setErr(true);
    }
  }, [kind, decoded]);

  if (err) return <EmptyState>查無此人（kind 僅支援 coach / umpire）。</EmptyState>;
  if (kind === "coach" && coach) {
    if (!coach.roles.length && !coach.manager_eras.length) return <EmptyState>查無此教練。</EmptyState>;
    return <CoachView d={coach} />;
  }
  if (kind === "umpire" && ump) {
    const hasAny = Object.values(ump.positions).some((v) => Number(v) > 0);
    if (!hasAny) return <EmptyState>查無此裁判（本季無執法紀錄）。</EmptyState>;
    return <UmpireView d={ump} />;
  }
  return <EmptyState>載入中…</EmptyState>;
}
