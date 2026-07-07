"use client";

import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { detail, type StatRow } from "@/lib/client";
import { fmtIPParts } from "@/lib/format";
import GameBoard, { type Live } from "@/components/game-board";
import { WinProbChart, type WpPoint } from "@/components/win-prob-chart";
import { fanNick, teamColor, teamShort } from "@/lib/teams";
import { GameOverview, Pregame, type PregameMatchup } from "./overview";

const n = (v: number | string | null) => (v === null || v === undefined ? "" : Number(v));

const i0 = (v: number | string | null | undefined) => (v === null || v === undefined ? "—" : String(v));
const ipTxt = (r: StatRow) => fmtIPParts(r.inning_pitched_cnt as number | null, r.inning_pitched_div3 as number | null);

// 打者亮點標記：滿貫/猛打賞(3安+)/致勝打點/MVP
function batterMark(r: StatRow): string {
  const t: string[] = [];
  if (n(r.grand_slam) as number) t.push("滿貫");
  if ((n(r.hits) as number) >= 3) t.push("猛打賞");
  if (n(r.gw_rbi) as number) t.push("致勝打點");
  if (r.is_mvp) t.push("MVP");
  return t.join("·");
}

function BoxBatting({ rows, team }: { rows: StatRow[]; team: string }) {
  const cols: [string, (r: StatRow) => string][] = [
    ["AB", (r) => i0(r.at_bats)], ["R", (r) => i0(r.runs)], ["H", (r) => i0(r.hits)],
    ["2B", (r) => i0(r.doubles)], ["3B", (r) => i0(r.triples)], ["HR", (r) => i0(r.home_runs)],
    ["打點", (r) => i0(r.rbi)], ["BB", (r) => i0(r.bb)], ["SO", (r) => i0(r.so)], ["SB", (r) => i0(r.sb)],
  ];
  return (
    <div className="overflow-x-auto rounded-xl border border-line bg-surface">
      <table className="w-full text-sm">
        <thead className="bg-surface-2 text-left text-muted">
          <tr><th className="px-3 py-2 font-medium">{team}　打者</th>
            {cols.map(([h]) => <th key={h} className="px-2 py-2 text-right font-medium">{h}</th>)}</tr>
        </thead>
        <tbody className="font-mono tabular-nums">
          {rows.map((r, i) => {
            const mark = batterMark(r);
            return (
              <tr key={i} className="border-t border-line">
                <td className="whitespace-nowrap px-3 py-1.5 font-sans text-ink">{String(r.hitter_name ?? "")}
                  <span className="ml-1 text-[10px] text-faint">{String(r.role_type ?? "")}</span>
                  {mark && <span className="ml-1 text-[10px] font-semibold text-cpbl">{mark}</span>}</td>
                {cols.map(([h, f]) => <td key={h} className="px-2 py-1.5 text-right">{f(r)}</td>)}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// 投手結果標記：勝/敗官方、中繼官方(relief_point)；救援/中繼失敗依規則情境自 livelog 推算。
// 回傳 token 陣列（成敗、色調），救援/中繼失敗標紅。
const MARK: Record<string, { text: string; tone: "pos" | "neg" }> = {
  W: { text: "勝", tone: "pos" }, L: { text: "敗", tone: "neg" },
  SV: { text: "SV", tone: "pos" }, HLD: { text: "H", tone: "pos" },
  BS: { text: "救援失敗", tone: "neg" }, BH: { text: "中繼失敗", tone: "neg" },
};
function pitcherMarks(r: StatRow, decisions: Record<string, string>): { text: string; tone: "pos" | "neg" }[] {
  const out: { text: string; tone: "pos" | "neg" }[] = [];
  const d = decisions[String(r.pitcher_acnt)];
  if (d) for (const tok of d.split("·")) if (MARK[tok]) out.push(MARK[tok]);
  if (r.is_complete_game) out.push({ text: r.is_shutout ? "完封" : "完投", tone: "pos" });
  return out;
}

function BoxPitching({ rows, team, decisions }: { rows: StatRow[]; team: string; decisions: Record<string, string> }) {
  const cols: [string, (r: StatRow) => string][] = [
    ["IP", ipTxt], ["H", (r) => i0(r.hits)], ["R", (r) => i0(r.runs)], ["ER", (r) => i0(r.earned_runs)],
    ["BB", (r) => i0(r.bb)], ["SO", (r) => i0(r.so)], ["被HR", (r) => i0(r.home_runs)],
    ["球數", (r) => i0(r.pitch_cnt)], ["最快", (r) => (r.max_speed ? `${r.max_speed}` : "—")],
  ];
  return (
    <div className="overflow-x-auto rounded-xl border border-line bg-surface">
      <table className="w-full text-sm">
        <thead className="bg-surface-2 text-left text-muted">
          <tr><th className="px-3 py-2 font-medium">{team}　投手</th>
            {cols.map(([h]) => <th key={h} className="px-2 py-2 text-right font-medium">{h}</th>)}</tr>
        </thead>
        <tbody className="font-mono tabular-nums">
          {rows.map((r, i) => {
            const marks = pitcherMarks(r, decisions);
            return (
              <tr key={i} className="border-t border-line">
                <td className="whitespace-nowrap px-3 py-1.5 font-sans text-ink">{String(r.pitcher_name ?? "")}
                  {marks.map((m, j) => (
                    <span key={j} className={`ml-1 text-[10px] font-semibold ${m.tone === "neg" ? "text-[#C8102E]" : "text-accent"}`}>{m.text}</span>
                  ))}</td>
                {cols.map(([h, f]) => <td key={h} className="px-2 py-1.5 text-right">{f(r)}</td>)}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export default function GameLivePage() {
  const { sno } = useParams<{ sno: string }>();
  const sp = useSearchParams();
  const kind = sp.get("kind") || "A";
  const year = sp.get("year") ? Number(sp.get("year")) : undefined;
  const [data, setData] = useState<Live | null>(null);
  const [err, setErr] = useState(false);
  const [idx, setIdx] = useState(0);
  // 頁面預設「比賽總覽」；逐打席為進階操作視圖
  const [view, setView] = useState<"overview" | "pbp">("overview");
  const [wp, setWp] = useState<WpPoint[] | null>(null);
  const [pregame, setPregame] = useState<PregameMatchup | null>(null);

  useEffect(() => {
    detail.gameLive(Number(sno), kind, year)
      .then((d) => {
        const dd = d as Live;
        setData(dd);
        setIdx(Math.max(0, dd.livelog.length - 1)); // 逐打席視圖預設停在終局
        // 未開賽（無逐打席）→ 抓賽前展望（賽果模型近期對戰卡，比 date+主隊碼）
        if (!dd.livelog.length && dd.game) {
          const gd = String(dd.game.game_date ?? "");
          const hc = String(dd.game.home_team_code ?? "");
          detail.outcomeToday()
            .then((o) => setPregame(o.items.find((it) =>
              it.game_date === gd && it.home.code === hc) ?? null))
            .catch(() => setPregame(null));
        }
      })
      .catch(() => setErr(true));
    detail.winprob(Number(sno), kind, year).then((d) => setWp(d.items)).catch(() => setWp([]));
  }, [sno, kind, year]);

  // 總覽點關鍵時刻/得分時刻/勝率曲線 → 跳到該打席（切逐打席視圖 + 捲到操作區）
  const jumpToPa = (evt: string) => {
    const i = data?.livelog.findIndex((e) => String(e.main_event_no) === evt) ?? -1;
    if (i < 0) return;
    setIdx(i);
    setView("pbp");
    requestAnimationFrame(() =>
      document.getElementById("pbp-section")?.scrollIntoView({ behavior: "smooth", block: "start" }));
  };

  if (err) return <p className="text-sm text-muted">載入賽況失敗。</p>;
  if (!data) return <p className="text-sm text-faint">載入中…</p>;
  if (!data.game) return <p className="text-sm text-muted">查無此場比賽。</p>;

  const g = data.game;

  // 本場焦點（門檻原則＝一季只會出現幾次才配當焦點）：
  // 賽事級（再見/逆轉/延長/和局/合力完封）→ 打者 → 投手 → 球速（≥155 才顯示）。
  const highlights: string[] = [];
  const hs = n(g.home_score) as number;
  const aw = n(g.away_score) as number;
  const completed = hs + aw > 0;
  if (completed) {
    // 再見（主隊勝且全場最後一個得分事件在主隊末攻）：從末得分事件的 action_name 定名
    if (hs > aw) {
      const scores = data.livelog.filter((r) => r.is_score && !r.is_change_player);
      const lastScore = scores[scores.length - 1];
      const after = lastScore ? data.livelog.slice(data.livelog.indexOf(lastScore) + 1) : [];
      const isLastPlay = !!lastScore && String(lastScore.visiting_home_type) === "2"
        && !after.some((r) => r.hitter_acnt && !r.is_change_player
            && String(r.main_event_no) !== String(lastScore.main_event_no) && !r.is_score
            && !/比賽結束/.test(String(r.content ?? "")));
      if (isLastPlay) {
        const a = String(lastScore.action_name ?? "");
        const label = a.includes("全壘打") ? "再見全壘打" : a.includes("安打") ? "再見安打"
          : a.includes("四壞") ? "再見四壞" : a.includes("觸身") ? "再見觸身球"
          : a.includes("犧牲") ? "再見犧牲打" : "再見勝";
        highlights.push(`${String(lastScore.hitter_name ?? "")} ${label}`);
      }
    }
    // 逆轉勝（勝隊曾落後 ≥3 分）：逐半局累計比分掃最大落後
    if (hs !== aw) {
      const cum = { a: 0, h: 0 };
      let maxDef = 0;
      const winnerHome = hs > aw;
      const innings = [...new Set(data.scoreboard.map((r) => n(r.inning_seq) as number))].sort((x, y) => x - y);
      for (const inn of innings) {
        for (const half of ["1", "2"]) {
          const row = data.scoreboard.find((r) => (n(r.inning_seq) as number) === inn
            && String(r.visiting_home_type) === half);
          if (!row) continue;
          if (half === "1") cum.a += n(row.score_cnt) as number;
          else cum.h += n(row.score_cnt) as number;
          maxDef = Math.max(maxDef, winnerHome ? cum.a - cum.h : cum.h - cum.a);
        }
      }
      if (maxDef >= 3) highlights.push(`落後 ${maxDef} 分逆轉勝`);
    }
    const maxInn = Math.max(0, ...data.scoreboard.map((r) => n(r.inning_seq) as number));
    if (hs === aw) highlights.push(`${maxInn} 局和局`);       // 含未滿 9 局的裁定和局
    else if (maxInn > 9) highlights.push(`延長 ${maxInn} 局`);
    // 合力完封（敗方 0 分且勝方無單人完投）
    if (hs !== aw && Math.min(hs, aw) === 0) {
      const winSide = hs > aw ? "2" : "1";
      const staff = data.pitching.filter((r) => String(r.visiting_home_type) === winSide);
      if (staff.length > 1 && !staff.some((r) => r.is_complete_game)) highlights.push("合力完封");
    }
  }
  // 裁定比賽（未打滿正常局數即終結；和局正常須 12 局、勝負正常須 9 局起）
  if (completed && data.scoreboard.length > 0) {
    const maxInn0 = Math.max(0, ...data.scoreboard.map((r) => n(r.inning_seq) as number));
    if (hs !== aw && maxInn0 < 9) highlights.push(`${maxInn0} 局裁定比賽`);
  }
  // 魯閣（網路用語，源自大魯閣打擊場＝投手像發球機一樣好打）：
  // 單場失 10 分以上＝被打爆隊的暱稱前綴+魯閣；失 20 分以上＝雙魯閣。非官方、含嘲諷意味。
  if (completed) {
    const lukaku = (concededBy: string | null | undefined, runsAgainst: number) => {
      if (runsAgainst < 10) return;
      const p = fanNick(String(concededBy ?? ""))?.prefix ?? "";
      highlights.push(runsAgainst >= 20 ? `雙${p}魯閣（失 ${runsAgainst} 分）` : `${p}魯閣（失 ${runsAgainst} 分）`);
    };
    lukaku(g.away_team_code as string, hs);   // 主隊得 10+ → 客隊被打爆
    lukaku(g.home_team_code as string, aw);   // 客隊得 10+ → 主隊被打爆
  }
  // 中計（網路用語）：滿壘卻未得分收場；大中計＝無人出局滿壘未得分。
  // 比分欄=事件後快照 → 滿壘點的「當下分數」須用前一列事件後分（防首球滿貫誤判）。
  if (completed && data.livelog.length > 0) {
    const pre = new Map<StatRow, number>();
    let pv = 0, ph = 0;
    for (const r of data.livelog) {
      pre.set(r, String(r.visiting_home_type) === "1" ? pv : ph);
      pv = r.visiting_score != null ? (n(r.visiting_score) as number) : pv;
      ph = r.home_score != null ? (n(r.home_score) as number) : ph;
    }
    const byHalf = new Map<string, StatRow[]>();
    for (const r of data.livelog) {
      const k = `${r.inning_seq}|${r.visiting_home_type}`;
      if (!byHalf.has(k)) byHalf.set(k, []);
      byHalf.get(k)!.push(r);
    }
    const traps: Record<string, { normal: number; big: number }> = { "1": { normal: 0, big: 0 }, "2": { normal: 0, big: 0 } };
    for (const [k, rows] of byHalf) {
      const vht = k.split("|")[1];
      const post = vht === "1" ? "visiting_score" : "home_score";
      const endScore = Math.max(0, ...rows.map((r) => (n(r[post]) as number) || 0));
      let prevHitter = "", trapped: "big" | "normal" | null = null;
      for (const r of rows) {
        if (r.is_change_player || !r.hitter_acnt) continue;
        if (String(r.hitter_acnt) !== prevHitter) {           // 打席首事件
          prevHitter = String(r.hitter_acnt);
          const loaded = r.first_base && r.second_base && r.third_base;
          if (loaded && endScore - (pre.get(r) ?? 0) === 0) {
            trapped = (n(r.out_cnt) as number) === 0 ? "big" : (trapped ?? "normal");
          }
        }
      }
      if (trapped) traps[vht][trapped === "big" ? "big" : "normal"]++;
    }
    for (const [vht, t] of Object.entries(traps)) {
      const team = teamShort(String(vht === "1" ? g.away_team_code : g.home_team_code));
      if (t.big) highlights.push(`${team} 大中計${t.big > 1 ? ` ×${t.big}` : ""}（無人出局滿壘未得分）`);
      if (t.normal) highlights.push(`${team} 中計${t.normal > 1 ? ` ×${t.normal}` : ""}（滿壘未得分）`);
    }
  }
  // 煮粥（網路用語）：單局 2 次以上失誤（守備一鍋粥）。scoreboard 逐局 E 直接判。
  if (completed) {
    for (const r of data.scoreboard) {
      if ((n(r.error_cnt) as number) >= 2) {
        const team = teamShort(String(String(r.visiting_home_type) === "1" ? g.away_team_code : g.home_team_code));
        highlights.push(`${team} 煮粥（${n(r.inning_seq)} 局 ${r.error_cnt} 失誤）`);
      }
    }
  }
  for (const r of data.batting) {
    const nm = String(r.hitter_name ?? "");
    const hr = n(r.home_runs) as number;
    const h = n(r.hits) as number;
    if (n(r.grand_slam) as number) highlights.push(`${nm} 滿貫砲`);
    else if (hr >= 2) highlights.push(`${nm} ${hr} 響砲`);
    // 術語：3安=猛打賞（box 內已標）、4安=鐵支、5安+ 直接報數
    if (h === 4) highlights.push(`${nm} 鐵支（單場4安）`);
    else if (h >= 5) highlights.push(`${nm} 單場 ${h} 安`);
    if ((n(r.rbi) as number) >= 4) highlights.push(`${nm} ${r.rbi} 打點`);
    if ((n(r.sb) as number) >= 2) highlights.push(`${nm} ${r.sb} 次盜壘`);
    // 致勝打點（官方 box 欄）：每場勝方必有，作為焦點區的保底內容
    if (n(r.gw_rbi) as number) highlights.push(`${nm} 致勝打點`);
  }
  for (const r of data.pitching) {
    const nm = String(r.pitcher_name ?? "");
    const d = (data.decisions ?? {})[String(r.pitcher_acnt)];
    if (r.is_shutout) highlights.push(`${nm} 完封`);
    else if (r.is_complete_game) highlights.push(`${nm} 完投`);
    if ((n(r.so) as number) >= 10) highlights.push(`${nm} ${r.so} 次三振`);
    // 問天（網路用語）：優質先發（≥6 局、自責 ≤3）卻吞敗或無關勝負
    const isStarter = String(r.pitcher_acnt) === String(g.away_starter_id)
      || String(r.pitcher_acnt) === String(g.home_starter_id);
    const outs = (n(r.inning_pitched_cnt) as number) * 3 + (n(r.inning_pitched_div3) as number);
    if (completed && isStarter && outs >= 18 && (n(r.earned_runs) as number) <= 3 && d !== "W") {
      highlights.push(`${nm} 問天（優質先發${d === "L" ? "吞敗" : "無關勝負"}）`);
    }
    // 劇場（網路用語）：救援成功但過程驚險——讓 ≥2 人上壘或有失分
    if (d === "SV") {
      const runners = (n(r.hits) as number) + (n(r.bb) as number) + (n(r.hbp) as number);
      if (runners >= 2 || (n(r.runs) as number) >= 1) highlights.push(`${nm} 劇場`);
    }
  }
  // 最速球：≥155 才有焦點價值（日常最速無鑑別度）
  const maxSp = Math.max(0, ...data.pitching.map((r) => (n(r.max_speed) as number) || 0));
  if (maxSp >= 155) highlights.push(`最速球 ${maxSp} km/h`);
  highlights.splice(10);

  // MVP 當場成績行（打者/投手 box 內 is_mvp）
  const mvpBat = data.batting.find((r) => r.is_mvp);
  const mvpPit = data.pitching.find((r) => r.is_mvp);
  let mvp: { name: string; line: string } | null = null;
  if (mvpBat) {
    const parts = [`${n(mvpBat.at_bats)} 打數 ${n(mvpBat.hits)} 安`];
    if (n(mvpBat.home_runs) as number) parts.push(`${mvpBat.home_runs} 轟`);
    if (n(mvpBat.rbi) as number) parts.push(`${mvpBat.rbi} 打點`);
    if (n(mvpBat.runs) as number) parts.push(`${mvpBat.runs} 得分`);
    if (n(mvpBat.sb) as number) parts.push(`${mvpBat.sb} 盜`);
    mvp = { name: String(mvpBat.hitter_name ?? ""), line: parts.join("・") };
  } else if (mvpPit) {
    const parts = [`${ipTxt(mvpPit)} 局`, `${n(mvpPit.so)}K`, `失 ${n(mvpPit.runs)} 分`];
    if ((n(mvpPit.bb) as number) === 0) parts.push("無保送");
    mvp = { name: String(mvpPit.pitcher_name ?? ""), line: parts.join("・") };
  }

  // 決勝資訊（併入焦點卡；歷史無逐打席場次仍走頁面下方 strip）
  const ppl = data.people;
  const holdNames = Object.entries(data.decisions ?? {})
    .filter(([, v]) => v === "HLD")
    .map(([acnt]) => data.pitching.find((r) => String(r.pitcher_acnt) === acnt)?.pitcher_name)
    .filter(Boolean).join("、");
  const decisionItems: [string, string][] = ([
    ["先發(客)", ppl[String(g.away_starter_id)]],
    ["先發(主)", ppl[String(g.home_starter_id)]],
    ["勝投", ppl[String(g.winning_pitcher_id)]],
    ["敗投", ppl[String(g.losing_pitcher_id)]],
    ["救援", ppl[String(g.closer_id)]],
    ["中繼", holdNames ? `${holdNames}（推算）` : undefined],
  ] as [string, string | undefined][]).filter(([, v]) => v) as [string, string][];

  // 賽事資訊（渲染於總覽右卡）：天氣/觀眾/時長併一列，裁判獨立一列
  const info: [string, string][] = [];
  if (data.detail) {
    const d = data.detail;
    const parts: string[] = [];
    const wx = String(d.weather_desc ?? "");
    if (wx) {
      const cond = wx.split("。")[0] ?? "";
      const temp = wx.match(/攝氏(\d+)至(\d+)度/);
      const icon = /雷|雨/.test(cond) ? "🌧️" : /多雲/.test(cond) ? "⛅"
        : /陰/.test(cond) ? "☁️" : /晴/.test(cond) ? "☀️" : "🌡️";
      parts.push(`${icon} ${cond}${temp ? ` ${temp[1]}–${temp[2]}°C` : ""}`);
    }
    if (d.attendance) parts.push(`觀眾 ${Number(d.attendance).toLocaleString()} 人`);
    if (d.game_time) parts.push(`時長 ${String(d.game_time)}`);
    if (parts.length) info.push(["資訊", parts.join("・")]);
    const umps = [["主審", d.head_umpire], ["一壘", d.first_umpire], ["二壘", d.second_umpire],
      ["三壘", d.third_umpire], ["左審", d.left_umpire], ["右審", d.right_umpire]]
      .filter(([, v]) => v).map(([l, v]) => `${l} ${v}`).join("、");
    if (umps) info.push(["裁判", umps]);
  }

  return (
    <div>
      <Link href="/games" className="text-xs text-faint hover:text-accent">← 返回賽況列表</Link>

      {data.livelog.length > 0 ? (
        <section className="mb-8 mt-2 space-y-4">
          <GameBoard data={data} idx={idx} setIdx={setIdx} view={view}
            onNavigate={() => setView("pbp")}
            toolbar={
              <div className="inline-flex gap-1 rounded-lg bg-surface-2 p-1">
                {([["overview", "比賽總覽"], ["pbp", "逐打席"]] as const).map(([v, label]) => (
                  <button key={v} onClick={() => setView(v)}
                    className={`rounded-md px-3 py-1 text-sm transition ${view === v ? "bg-ink text-white" : "text-muted hover:text-ink"}`}>
                    {label}
                  </button>
                ))}
              </div>
            } />
          {view === "overview" && (
            <>
              <GameOverview wp={wp ?? []} log={data.livelog}
                homeName={String(g.home_team_name)} awayName={String(g.away_team_name)}
                onJump={jumpToPa} highlights={highlights} info={info}
                mvp={mvp} decisions={decisionItems} />
              <WinProbChart items={wp ?? []}
                homeName={String(g.home_team_name)} awayName={String(g.away_team_name)}
                homeColor={teamColor(String(g.home_team_code ?? ""))} onSelect={jumpToPa} />
            </>
          )}
        </section>
      ) : ((n(g.home_score) as number) + (n(g.away_score) as number)) > 0 ? (
        /* 已完賽但無逐打席（歷史場）：沿用比分標題 */
        <header className="mb-6 mt-2">
          <h1 className="text-2xl font-bold">
            {String(g.away_team_name)} <span className="font-mono">{n(g.away_score)}</span>
            <span className="mx-2 text-faint">@</span>
            {String(g.home_team_name)} <span className="font-mono">{n(g.home_score)}</span>
          </h1>
          <p className="mt-1 text-sm text-muted">{String(g.game_date ?? "")}　{String(g.venue ?? "")}</p>
        </header>
      ) : (
        /* 未開賽：賽前展望（賽果模型對戰卡） */
        <div className="mb-8 mt-2 space-y-4">
          <header>
            <h1 className="text-2xl font-bold">
              {String(g.away_team_name)} <span className="mx-2 text-faint">@</span>
              {String(g.home_team_name)}
            </h1>
            <p className="mt-1 text-sm text-muted">{String(g.game_date ?? "")}　{String(g.venue ?? "")}　尚未開賽</p>
          </header>
          {pregame && <Pregame m={pregame} />}
        </div>
      )}

      {g.delay_kind && (() => {
        const md = (s: unknown) => {
          const p = String(s ?? "").slice(5).split("-");
          return p.length === 2 ? `${+p[0]}/${+p[1]}` : "";
        };
        const orig = md(g.orig_date);
        const played = md(g.game_date);
        const done = n(g.present_status) === 1 && ((n(g.home_score) as number) + (n(g.away_score) as number)) > 0;
        const note = g.delay_kind === "保留"
          ? `因雨保留比賽　原 ${orig} 開賽${done ? `，${played} 續賽完成` : "，擇期續賽"}`
          : `因雨延賽　原定 ${orig}${done && played !== orig ? `，${played} 補賽` : "，擇期補賽"}`;
        return (
          <div className="mb-6 flex items-center gap-2 rounded-xl border border-amber-300 bg-amber-50 px-4 py-2.5 text-sm text-amber-900">
            <span>☔</span><span className="font-medium">{note}</span>
          </div>
        );
      })()}

      {/* 決勝資訊已併入總覽焦點卡；僅歷史無逐打席場次（無總覽）時在此顯示 */}
      {data.livelog.length === 0 && (decisionItems.length > 0 || mvp) && (
        <div className="mb-6 flex flex-wrap gap-x-5 gap-y-1.5 rounded-xl border border-line bg-surface px-4 py-3 text-sm">
          {decisionItems.map(([l, v]) => (
            <span key={l}><span className="text-muted">{l}</span> <span className="font-medium text-ink">{v}</span></span>
          ))}
          {ppl[String(g.mvp_id)] && (
            <span><span className="text-muted">MVP</span> <span className="font-medium text-ink">{ppl[String(g.mvp_id)]}</span></span>
          )}
        </div>
      )}

      {/* 本場焦點 / 賽事資訊 已整併進總覽右卡（GameOverview），此處不重複 */}

      {data.batting.length > 0 && (
        <section className="mb-8">
          <h2 className="mb-3 text-lg font-semibold">Box Score</h2>
          <div className="grid gap-4 lg:grid-cols-2">
            <BoxBatting rows={data.batting.filter((r) => String(r.visiting_home_type) === "1")} team={String(g.away_team_name)} />
            <BoxBatting rows={data.batting.filter((r) => String(r.visiting_home_type) === "2")} team={String(g.home_team_name)} />
            <BoxPitching rows={data.pitching.filter((r) => String(r.visiting_home_type) === "1")} team={String(g.away_team_name)} decisions={data.decisions ?? {}} />
            <BoxPitching rows={data.pitching.filter((r) => String(r.visiting_home_type) === "2")} team={String(g.home_team_name)} decisions={data.decisions ?? {}} />
          </div>
        </section>
      )}
    </div>
  );
}
