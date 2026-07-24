"use client";

import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { detail, type StatRow } from "@/lib/client";
import { fmtIPParts } from "@/lib/format";
import GameBoard, { type Live } from "@/components/game-board";
import { Card, Eyebrow, Notice, Skeleton, ErrorState, EmptyState, PlayerLink, ENTITY_LINK } from "@/components/ui";
import BoxTabs from "./box-tabs";
import { WinProbChart, type WpPoint } from "@/components/win-prob-chart";
import { PregameCard } from "@/components/pregame-card";
import { fanNick, teamColor, teamShort } from "@/lib/teams";
import { resolvePregameCard, type PregameCardModel } from "@/lib/pregame-card";
import { GameOverview, type DecItem } from "./overview";
import { StartingLineups } from "@/components/starting-lineups";

const n = (v: number | string | null) => (v === null || v === undefined ? "" : Number(v));

const ipTxt = (r: StatRow) => fmtIPParts(r.inning_pitched_cnt as number | null, r.inning_pitched_div3 as number | null);

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
  const [pregame, setPregame] = useState<PregameCardModel | null>(null);
  const [milestones, setMilestones] = useState<{ player: string; text: string }[]>([]);

  useEffect(() => {
    detail.gameLive(Number(sno), kind, year)
      .then((d) => {
        const dd = d as Live;
        setData(dd);
        setIdx(Math.max(0, dd.livelog.length - 1)); // 逐打席視圖預設停在終局
        // 未開賽（無逐打席）→ 固定語意的賽前勝率，不再使用可選特徵對戰 API。
        if (!dd.livelog.length && dd.game) {
          const game = dd.game;
          detail.pregame()
            .then((response) => setPregame(resolvePregameCard({
              response,
              game: {
                season: Number(game.year),
                game_sno: Number(game.game_sno),
                kind_code: String(game.kind_code),
              },
            })))
            .catch(() => setPregame(resolvePregameCard({
              response: null,
              fetchFailed: true,
              game: {
                season: Number(game.year),
                game_sno: Number(game.game_sno),
                kind_code: String(game.kind_code),
              },
            })));
        }
      })
      .catch(() => setErr(true));
    detail.winprob(Number(sno), kind, year).then((d) => setWp(d.items)).catch(() => setWp([]));
    detail.milestones(Number(sno), kind, year).then((d) => setMilestones(d.items)).catch(() => setMilestones([]));
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

  if (err) return <ErrorState>載入賽況失敗。</ErrorState>;
  // 載入骨架：對齊記分條(rounded-2xl)＋linescore＋總覽雙卡的量體，避免 CLS
  if (!data) return (
    <div className="mt-2 space-y-4">
      <Skeleton className="h-28 rounded-2xl" />
      <Skeleton className="h-24 rounded-xl" />
      <div className="grid gap-4 lg:grid-cols-2">
        <Skeleton className="h-40 rounded-xl" /><Skeleton className="h-40 rounded-xl" />
      </div>
    </div>
  );
  if (!data.game) return <EmptyState>查無此場比賽。</EmptyState>;

  const g = data.game;

  // 本場焦點（門檻原則＝一季只會出現幾次才配當焦點）：
  // 賽事級（再見/逆轉/延長/和局/合力完封）→ 打者 → 投手 → 球速（≥155 才顯示）。
  // 每條焦點帶所屬隊伍 code（供前端上色）；賽事級/中性（和局/延長/裁定/里程碑）team=null。
  const highlights: { text: string; team: string | null }[] = [];
  const teamOf = (vht: unknown) =>
    String(vht) === "1" ? String(g.away_team_code ?? "") : String(g.home_team_code ?? "");
  const H = (text: string, team: string | null = null) => highlights.push({ text, team });
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
        H(`${String(lastScore.hitter_name ?? "")} ${label}`, String(g.home_team_code ?? ""));
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
      if (maxDef >= 3) H(`落後 ${maxDef} 分逆轉勝`, String((winnerHome ? g.home_team_code : g.away_team_code) ?? ""));
    }
    const maxInn = Math.max(0, ...data.scoreboard.map((r) => n(r.inning_seq) as number));
    if (hs === aw) H(`${maxInn} 局和局`);       // 含未滿 9 局的裁定和局（中性）
    else if (maxInn > 9) H(`延長 ${maxInn} 局`);
    // 合力完封（敗方 0 分且勝方無單人完投）
    if (hs !== aw && Math.min(hs, aw) === 0) {
      const winSide = hs > aw ? "2" : "1";
      const staff = data.pitching.filter((r) => String(r.visiting_home_type) === winSide);
      if (staff.length > 1 && !staff.some((r) => r.is_complete_game))
        H("合力完封", String((winSide === "2" ? g.home_team_code : g.away_team_code) ?? ""));
    }
  }
  // 裁定比賽（未打滿正常局數即終結；和局正常須 12 局、勝負正常須 9 局起）
  if (completed && data.scoreboard.length > 0) {
    const maxInn0 = Math.max(0, ...data.scoreboard.map((r) => n(r.inning_seq) as number));
    if (hs !== aw && maxInn0 < 9) H(`${maxInn0} 局裁定比賽`);
  }
  // 賽事級焦點（再見/逆轉/延長/和局/合力完封/裁定）數量錨點：稀有成就（extra）插在其後、
  // 常見焦點（魯閣/中計/猛打賞…）之前，確保稀有標籤不被 splice(12) 擠掉。
  const nGameLevel = highlights.length;
  // 魯閣（網路用語，源自大魯閣打擊場＝投手像發球機一樣好打）：
  // 單場失 10 分以上＝被打爆隊的暱稱前綴+魯閣；失 20 分以上＝雙魯閣。非官方、含嘲諷意味。
  if (completed) {
    const lukaku = (concededBy: string | null | undefined, runsAgainst: number) => {
      if (runsAgainst < 10) return;
      const p = fanNick(String(concededBy ?? ""))?.prefix ?? "";
      H(runsAgainst >= 20 ? `雙${p}魯閣（失 ${runsAgainst} 分）` : `${p}魯閣（失 ${runsAgainst} 分）`,
        String(concededBy ?? ""));
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
      const code = String((vht === "1" ? g.away_team_code : g.home_team_code) ?? "");
      const team = teamShort(code);
      if (t.big) H(`${team} 大中計${t.big > 1 ? ` ×${t.big}` : ""}（無人出局滿壘未得分）`, code);
      if (t.normal) H(`${team} 中計${t.normal > 1 ? ` ×${t.normal}` : ""}（滿壘未得分）`, code);
    }
  }
  // 煮粥（網路用語）：單局 2 次以上失誤（守備一鍋粥）。scoreboard 逐局 E 直接判。
  if (completed) {
    for (const r of data.scoreboard) {
      if ((n(r.error_cnt) as number) >= 2) {
        const code = teamOf(r.visiting_home_type);
        highlights.push({ text: `${teamShort(code)} 煮粥（${n(r.inning_seq)} 局 ${r.error_cnt} 失誤）`, team: code });
      }
    }
  }
  for (const r of data.batting) {
    const nm = String(r.hitter_name ?? "");
    const tm = teamOf(r.visiting_home_type);
    const hr = n(r.home_runs) as number;
    const h = n(r.hits) as number;
    if (n(r.grand_slam) as number) H(`${nm} 滿貫砲`, tm);
    else if (hr >= 2) H(`${nm} ${hr} 響砲`, tm);
    // 術語：3安=猛打賞、4安=鐵支、5安+ 直接報數
    if (h === 3) H(`${nm} 猛打賞`, tm);
    else if (h === 4) H(`${nm} 鐵支（單場4安）`, tm);
    else if (h >= 5) H(`${nm} 單場 ${h} 安`, tm);
    if ((n(r.rbi) as number) >= 4) H(`${nm} ${r.rbi} 打點`, tm);
    if ((n(r.sb) as number) >= 2) H(`${nm} ${r.sb} 次盜壘`, tm);
    // 致勝打點已移至決勝資訊列（勝投/敗投/救援同排），此處不再重複進焦點
  }
  for (const r of data.pitching) {
    const nm = String(r.pitcher_name ?? "");
    const tm = teamOf(r.visiting_home_type);
    const d = (data.decisions ?? {})[String(r.pitcher_acnt)];
    if (r.is_shutout) H(`${nm} 完封`, tm);
    else if (r.is_complete_game) H(`${nm} 完投`, tm);
    if ((n(r.so) as number) >= 8) H(`${nm} ${r.so} 次三振`, tm);
    // 問天（網路用語）：優質先發（≥6 局、自責 ≤3）卻吞敗或無關勝負
    const isStarter = String(r.pitcher_acnt) === String(g.away_starter_id)
      || String(r.pitcher_acnt) === String(g.home_starter_id);
    const outs = (n(r.inning_pitched_cnt) as number) * 3 + (n(r.inning_pitched_div3) as number);
    if (completed && isStarter && outs >= 18 && (n(r.earned_runs) as number) <= 3 && d !== "W") {
      H(`${nm} 問天（優質先發${d === "L" ? "吞敗" : "無關勝負"}）`, tm);
    }
    // 劇場（網路用語）：救援成功但過程驚險——讓 ≥2 人上壘或有失分
    if (d === "SV") {
      const runners = (n(r.hits) as number) + (n(r.bb) as number) + (n(r.hbp) as number);
      if (runners >= 2 || (n(r.runs) as number) >= 1) H(`${nm} 劇場`, tm);
    }
  }
  // 最速球：≥155 才有焦點價值（日常最速無鑑別度）
  const maxSp = Math.max(0, ...data.pitching.map((r) => (n(r.max_speed) as number) || 0));
  if (maxSp >= 155) {
    const fast = data.pitching.find((r) => (n(r.max_speed) as number) === maxSp);
    H(`最速球 ${maxSp} km/h`, fast ? teamOf(fast.visiting_home_type) : null);
  }
  // ───────── 焦點擴充（07-12：三振/效率/盜壘/上壘家族，全從 livelog+box 客戶端算，2018+）─────────
  const extra: { text: string; team: string | null }[] = [];
  if (completed && data.livelog.length > 0) {
    const pitchTeam = (half: string) => String((half === "1" ? g.home_team_code : g.away_team_code) ?? "");
    const batTeam = (half: string) => String((half === "1" ? g.away_team_code : g.home_team_code) ?? "");
    const pName = new Map<string, string>();
    for (const r of data.pitching) pName.set(String(r.pitcher_acnt), String(r.pitcher_name ?? ""));
    const hName = new Map<string, string>(), hTeam = new Map<string, string>();
    for (const r of data.batting) {
      hName.set(String(r.hitter_acnt), String(r.hitter_name ?? ""));
      hTeam.set(String(r.hitter_acnt), teamOf(r.visiting_home_type));
    }

    // 逐打席序列（PA 島＝連續同打者非換人事件，末筆為結果；沿用中計/pstats 島切法）
    type PA = { pitcher: string; hitter: string; inning: number; half: string; isK: boolean; onBase: boolean; retired: boolean };
    const paList: PA[] = [];
    let cur: StatRow | null = null;
    const flushPA = () => {
      if (!cur) return;
      const a = String(cur.action_name ?? "");
      const onBase = /安打|全壘打|四壞|敬遠|觸身/.test(a);              // 乾淨上壘（安打/四死）
      const reachedAny = onBase || /失誤|野手選擇|野選|妨礙/.test(a);   // 含失誤/野選上壘 → 破壞連續解決
      paList.push({
        pitcher: String(cur.pitcher_acnt ?? ""), hitter: String(cur.hitter_acnt ?? ""),
        inning: n(cur.inning_seq) as number, half: String(cur.visiting_home_type ?? ""),
        isK: /三振/.test(a), onBase, retired: !reachedAny,
      });
      cur = null;
    };
    for (const r of data.livelog) {
      if (r.is_change_player || !r.hitter_acnt) continue;
      if (cur && String(cur.hitter_acnt) !== String(r.hitter_acnt)) flushPA();
      cur = r;
    }
    flushPA();
    const pHalf: Record<string, string> = {};
    for (const pa of paList) pHalf[pa.pitcher] = pa.half;

    // ①④ 連續三振 ≥5 / 連續解決 ≥6（per pitcher rolling，跨局；他隊打席不影響其連續）
    const kS: Record<string, number> = {}, kMax: Record<string, number> = {};
    const rS: Record<string, number> = {}, rMax: Record<string, number> = {};
    for (const pa of paList) {
      const p = pa.pitcher;
      kS[p] = pa.isK ? (kS[p] ?? 0) + 1 : 0; kMax[p] = Math.max(kMax[p] ?? 0, kS[p]);
      rS[p] = pa.retired ? (rS[p] ?? 0) + 1 : 0; rMax[p] = Math.max(rMax[p] ?? 0, rS[p]);
    }
    for (const [p, mx] of Object.entries(kMax))
      if (mx >= 5) extra.push({ text: `${pName.get(p) ?? ""} 連續 ${mx} 三振`, team: pitchTeam(pHalf[p]) });
    for (const [p, mx] of Object.entries(rMax))
      if (mx >= 6) extra.push({ text: `${pName.get(p) ?? ""} 連續解決 ${mx} 人`, team: pitchTeam(pHalf[p]) });

    // ② 單局三振（per pitcher×half ≥3K；寬版含上壘後補 K）
    const inK: Record<string, number> = {};
    for (const pa of paList) if (pa.isK) { const k = `${pa.pitcher}|${pa.inning}|${pa.half}`; inK[k] = (inK[k] ?? 0) + 1; }
    for (const [k, c] of Object.entries(inK)) if (c >= 3) {
      const [p, inn, half] = k.split("|");
      extra.push({ text: `${pName.get(p) ?? ""} ${inn} 局單局 ${c}K`, team: pitchTeam(half) });
    }

    // ⑦ 全打席上壘（PA ≥4 全上壘＝安打/四死；失誤/野選破壞）
    const paByH: Record<string, PA[]> = {};
    for (const pa of paList) (paByH[pa.hitter] ??= []).push(pa);
    for (const [h, list] of Object.entries(paByH))
      if (list.length >= 4 && list.every((x) => x.onBase))
        extra.push({ text: `${hName.get(h) ?? ""} ${list.length} 打席全上壘`, team: batTeam(list[0].half) });

    // ③ 三球關門（半局內單一投手 ≤3 球完成 3 出局；雙殺壓縮球數）。
    // 球數用 pitch_cnt（投手累計，界內球亦計；is_ball/is_strike 會漏界內球）。半局球數＝該半局末 − 進半局前該投手累計。
    const lastMaxByP: Record<string, number> = {};
    let curKey = "", curOut = 0, curMax: Record<string, number> = {};
    const closeHalf = () => {
      if (curKey) {
        const ps = Object.keys(curMax);
        if (curOut >= 3 && ps.length === 1) {
          const p = ps[0], pitches = curMax[p] - (lastMaxByP[p] ?? 0);
          if (pitches > 0 && pitches <= 3)
            extra.push({ text: `${pName.get(p) ?? ""} ${pitches} 球關門（${curKey.split("|")[0]} 局）`, team: pitchTeam(curKey.split("|")[1]) });
        }
        for (const p of ps) lastMaxByP[p] = curMax[p];
      }
      curMax = {}; curOut = 0;
    };
    for (const r of data.livelog) {
      const key = `${n(r.inning_seq)}|${r.visiting_home_type}`;
      if (key !== curKey) { closeHalf(); curKey = key; }
      const p = String(r.pitcher_acnt ?? ""), pc = n(r.pitch_cnt) as number;
      if (p && pc) curMax[p] = Math.max(curMax[p] ?? 0, pc);
      for (const m of String(r.content ?? "").matchAll(/(\d)人出局/g)) curOut = Math.max(curOut, Number(m[1]));
    }
    closeHalf();

    // ⑤⑥⑩ 盜壘家族（重用 sabr regex；「盜壘刺」＝失敗不含）
    const sbRe = /([一二三])壘跑者\*?([^\s盜]+?)\s*(?:雙)?盜壘上([二三])壘/g;
    const sbhRe = /三壘跑者\*?([^\s盜]+?)\s*(?:雙)?盜壘回本壘得分/;
    const runSteals: Record<string, { count: number; half: string; name: string }> = {};  // runner|inn|half
    for (const r of data.livelog) {
      const content = String(r.content ?? ""), half = String(r.visiting_home_type ?? ""), inn = n(r.inning_seq) as number;
      let evt = 0, m: RegExpExecArray | null; const re = new RegExp(sbRe);
      while ((m = re.exec(content))) {
        const name = m[2]; evt++;
        const key = `${name}|${inn}|${half}`;
        (runSteals[key] ??= { count: 0, half, name }).count++;
      }
      const mh = content.match(sbhRe);
      if (mh) {
        const name = mh[1]; evt++;
        extra.push({ text: `${name} 盜本壘`, team: batTeam(half) });
        const key = `${name}|${inn}|${half}`;
        (runSteals[key] ??= { count: 0, half, name }).count++;
      }
      if (evt >= 2) extra.push({ text: "雙盜壘", team: batTeam(half) });   // 同一球 ≥2 跑者盜成功
    }
    for (const v of Object.values(runSteals))
      if (v.count >= 2) extra.push({ text: `${v.name} 單局 ${v.count} 盜`, team: batTeam(v.half) });

    // ⑧ 先發全員安打（每隊 role_type=先發 全部 ≥1 安）
    for (const side of ["1", "2"]) {
      const st = data.batting.filter((r) => String(r.visiting_home_type) === side && String(r.role_type) === "先發");
      if (st.length >= 9 && st.every((r) => (n(r.hits) as number) >= 1)) {
        const code = teamOf(side);
        extra.push({ text: `${teamShort(code)} 先發全員安打`, team: code });
      }
    }

    // ⑨ 萬磁王（球迷用語：單場觸身 ≥2）。以 content『觸身死球』計（單一事件行）——
    // action_name 是打席層級值、同打席每列重複，數列會爆量（實測 8 觸身誤報）。
    const hbpBy: Record<string, number> = {};
    for (const r of data.livelog) if (/觸身死球/.test(String(r.content ?? ""))) {
      const h = String(r.hitter_acnt ?? ""); hbpBy[h] = (hbpBy[h] ?? 0) + 1;
    }
    for (const [h, c] of Object.entries(hbpBy))
      if (c >= 2) extra.push({ text: `${hName.get(h) ?? ""} 萬磁王（${c} 觸身）`, team: hTeam.get(h) ?? null });
  }
  // 去重：有「單局 N 盜」者，box 級「N 次盜壘」重複、移除
  const inningSteal = new Set(extra.filter((e) => / 單局 \d+ 盜$/.test(e.text)).map((e) => e.text.split(" ")[0]));
  if (inningSteal.size) {
    const dup = (t: string) => { const m = t.match(/^(\S+) \d+ 次盜壘$/); return !!m && inningSteal.has(m[1]); };
    for (let i = highlights.length - 1; i >= 0; i--) if (dup(highlights[i].text)) highlights.splice(i, 1);
  }
  // 稀有成就插在賽事級之後、常見焦點之前
  highlights.splice(nGameLevel, 0, ...extra);
  highlights.splice(12);
  // 生涯里程碑/首次（後端精確判定）獨立成「特殊紀錄」區，依球員本場所屬隊上色
  // （避免與中性 accent 紅色混淆成味全）。球員名 → visiting_home_type → 隊碼。
  const nameTeam = new Map<string, string>();
  for (const r of data.pitching) {
    const nm = String(r.pitcher_name ?? "");
    if (nm) nameTeam.set(nm, teamOf(r.visiting_home_type));
  }
  for (const r of data.batting) {
    const nm = String(r.hitter_name ?? "");
    if (nm) nameTeam.set(nm, teamOf(r.visiting_home_type));
  }
  const milestoneItems = milestones.map((m) => ({
    text: `🏆 ${m.player} ${m.text}`,
    team: nameTeam.get(m.player) ?? null,
  }));

  // 決勝資訊的本季累計次數（box score 慣例「本季第 N 勝/敗/救援/中繼/次 MVP」，含本場）
  const dc = data.decision_counts;

  // MVP 當場成績行（打者/投手 box 內 is_mvp）＋本季單場 MVP 次數
  const mvpBat = data.batting.find((r) => r.is_mvp);
  const mvpPit = data.pitching.find((r) => r.is_mvp);
  let mvp: { name: string; line: string; count?: number | null; pid?: string } | null = null;
  if (mvpBat) {
    const parts = [`${n(mvpBat.at_bats)} 打數 ${n(mvpBat.hits)} 安`];
    if (n(mvpBat.home_runs) as number) parts.push(`${mvpBat.home_runs} 轟`);
    if (n(mvpBat.rbi) as number) parts.push(`${mvpBat.rbi} 打點`);
    if (n(mvpBat.runs) as number) parts.push(`${mvpBat.runs} 得分`);
    if (n(mvpBat.sb) as number) parts.push(`${mvpBat.sb} 盜`);
    mvp = { name: String(mvpBat.hitter_name ?? ""), line: parts.join("・"), count: dc?.mvp, pid: String(mvpBat.hitter_acnt ?? "") };
  } else if (mvpPit) {
    const parts = [`${ipTxt(mvpPit)} 局`, `${n(mvpPit.so)}K`, `失 ${n(mvpPit.runs)} 分`];
    if ((n(mvpPit.bb) as number) === 0) parts.push("無保送");
    mvp = { name: String(mvpPit.pitcher_name ?? ""), line: parts.join("・"), count: dc?.mvp, pid: String(mvpPit.pitcher_acnt ?? "") };
  }

  // 決勝資訊（併入焦點卡；歷史無逐打席場次仍走頁面下方 strip）
  const ppl = data.people;
  const holdAcnts = Object.entries(data.decisions ?? {})
    .filter(([, v]) => v === "HLD").map(([acnt]) => acnt);
  const holdNames = holdAcnts
    .map((acnt) => data.pitching.find((r) => String(r.pitcher_acnt) === acnt)?.pitcher_name)
    .filter(Boolean).join("、");
  // 中繼次數：單一中繼投手才在其後標「第 N 中繼」；多人時名字已擠，省略避免爆格
  const holdNote = holdAcnts.length === 1 && dc?.hold?.[holdAcnts[0]]
    ? `第${dc.hold[holdAcnts[0]]}中繼` : undefined;
  // 致勝打點（官方 box gw_rbi 旗標；每場勝方通常一人，罕見多人以「、」併列）
  const gwRbiNames = data.batting
    .filter((r) => (n(r.gw_rbi) as number) > 0)
    .map((r) => String(r.hitter_name ?? ""))
    .filter(Boolean).join("、");
  const decisionItems: DecItem[] = ([
    { label: "先發(客)", value: ppl[String(g.away_starter_id)], pid: String(g.away_starter_id ?? "") },
    { label: "先發(主)", value: ppl[String(g.home_starter_id)], pid: String(g.home_starter_id ?? "") },
    { label: "勝投", value: ppl[String(g.winning_pitcher_id)], note: dc?.win ? `第${dc.win}勝` : undefined, pid: String(g.winning_pitcher_id ?? "") },
    { label: "敗投", value: ppl[String(g.losing_pitcher_id)], note: dc?.loss ? `第${dc.loss}敗` : undefined, pid: String(g.losing_pitcher_id ?? "") },
    { label: "救援", value: ppl[String(g.closer_id)], note: dc?.save ? `第${dc.save}救援` : undefined, pid: String(g.closer_id ?? "") },
    { label: "中繼", value: holdNames || undefined, note: holdNote },   // HLD 為官方 relief_point（中繼點）
    { label: "致勝打點", value: gwRbiNames || undefined },
  ] as DecItem[]).filter((d) => d.value);

  // 賽事資訊（渲染於總覽右卡）：天氣/觀眾/時長併一列，裁判獨立一列
  const info: [string, React.ReactNode][] = [];
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
    if (parts.length) info.push(["概況", parts.join("・")]);
    const umps = [["主審", d.head_umpire], ["一壘", d.first_umpire], ["二壘", d.second_umpire],
      ["三壘", d.third_umpire], ["左審", d.left_umpire], ["右審", d.right_umpire]]
      .filter(([, v]) => v) as [string, string][];
    if (umps.length) {
      info.push([
        "裁判",
        <span key="umps" className="flex flex-wrap gap-x-1.5 gap-y-0.5">
          {umps.map(([l, v], idx) => (
            <span key={l}>
              {idx > 0 && "、"}
              <span className="text-muted">{l}</span>{" "}
              <Link href={`/people/umpire/${encodeURIComponent(v)}`} className={ENTITY_LINK}>
                {v}
              </Link>
            </span>
          ))}
        </span>
      ]);
    }
  }
  // 延賽/保留說明：放進賽事資訊卡（裁判下方）；歷史無總覽場走頁面下方 Notice fallback
  let delayNote = "";
  if (g.delay_kind) {
    const md = (s: unknown) => { const p = String(s ?? "").slice(5).split("-"); return p.length === 2 ? `${+p[0]}/${+p[1]}` : ""; };
    const orig = md(g.orig_date), played = md(g.game_date);
    const doneD = n(g.present_status) === 1 && ((n(g.home_score) as number) + (n(g.away_score) as number)) > 0;
    delayNote = g.delay_kind === "保留"
      ? `原 ${orig} 開賽${doneD ? `，${played} 續賽完成` : "，擇期續賽"}`
      : `原定 ${orig}${doneD && played !== orig ? `，${played} 補賽` : "，擇期補賽"}`;
    info.push([String(g.delay_kind), `☔ ${delayNote}`]);
  }

  return (
    <div>
      {/* 頂列：返回（左）＋ 日期球場／視圖切換（右）——填滿右側空白、並收掉記分條底列與獨立切換列 */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Link href="/games" className="text-xs text-faint hover:text-accent">← 返回賽況列表</Link>
        {data.livelog.length > 0 && (
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
            <span className="text-xs text-faint">{String(g.game_date ?? "")}　賽事編號 {sno}　{String(g.venue ?? "")}</span>
            <div className="inline-flex gap-1 rounded-lg bg-surface-2 p-1">
              {([["overview", "比賽總覽"], ["pbp", "逐打席"]] as const).map(([v, label]) => (
                <button key={v} onClick={() => setView(v)}
                  className={`rounded-md px-3 py-1 text-sm transition ${view === v ? "bg-ink text-paper" : "text-muted hover:text-ink"}`}>
                  {label}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      {data.livelog.length > 0 ? (
        <section className="mb-8 mt-2 space-y-4">
          <GameBoard data={data} idx={idx} setIdx={setIdx} view={view} wp={wp ?? undefined}
            onNavigate={() => setView("pbp")} />
          {view === "overview" && (
            <>
              <GameOverview wp={wp ?? []} log={data.livelog}
                homeName={String(g.home_team_name)} awayName={String(g.away_team_name)}
                homeColor={teamColor(String(g.home_team_code ?? ""))}
                awayColor={teamColor(String(g.away_team_code ?? ""))}
                onJump={jumpToPa} highlights={highlights} milestones={milestoneItems} info={info}
                mvp={mvp} decisions={decisionItems} />
              <StartingLineups game={g} log={data.livelog} pitching={data.pitching} />
              <WinProbChart items={wp ?? []}
                homeName={String(g.home_team_name)} awayName={String(g.away_team_name)}
                homeColor={teamColor(String(g.home_team_code ?? ""))} onSelect={jumpToPa} />
            </>
          )}
        </section>
      ) : ((n(g.home_score) as number) + (n(g.away_score) as number)) > 0 ? (
        /* 已完賽但無逐打席（歷史場）：沿用比分標題 */
        <header className="mb-6 mt-2">
          <h1 className="text-2xl font-extrabold tracking-tight text-ink">
            {String(g.away_team_name)} <span className="font-mono">{n(g.away_score)}</span>
            <span className="mx-2 text-faint">@</span>
            {String(g.home_team_name)} <span className="font-mono">{n(g.home_score)}</span>
          </h1>
          <p className="mt-1.5 text-sm text-muted">{String(g.game_date ?? "")}　賽事編號 {sno}　{String(g.venue ?? "")}</p>
        </header>
      ) : (
        /* 未開賽：固定語意的賽前勝率 */
        <div className="mb-8 mt-2 space-y-4">
          <header className="mb-6">
            <h1 className="text-2xl font-extrabold tracking-tight text-ink">
              {String(g.away_team_name)} <span className="mx-2 text-faint">@</span>
              {String(g.home_team_name)}
            </h1>
            <p className="mt-1.5 text-sm text-muted">{String(g.game_date ?? "")}　賽事編號 {sno}　{String(g.venue ?? "")}　尚未開賽</p>
          </header>
          {pregame && <PregameCard model={pregame} homeName={String(g.home_team_name)} />}
        </div>
      )}

      {/* 延賽/保留：有總覽場已併入賽事資訊卡（裁判下方）；歷史無總覽場在此 fallback */}
      {g.delay_kind && delayNote && data.livelog.length === 0 && (
        <Notice className="mb-6" icon="☔">因雨{String(g.delay_kind)}　{delayNote}</Notice>
      )}

      {/* 決勝資訊已併入總覽焦點卡；僅歷史無逐打席場次（無總覽）時在此顯示 */}
      {data.livelog.length === 0 && (decisionItems.length > 0 || mvp) && (
        <Card padding="px-4 py-3" className="mb-6 flex flex-wrap gap-x-5 gap-y-1.5 text-sm">
          {decisionItems.map((d) => (
            <span key={d.label}><span className="text-muted">{d.label}</span>{" "}
              <span className="font-medium text-ink">{d.pid ? <PlayerLink pid={d.pid} name={d.value} className="hover:text-accent hover:underline" /> : d.value}</span>
              {d.note ? <span className="ml-1 text-xs text-muted">{d.note}</span> : null}</span>
          ))}
          {ppl[String(g.mvp_id)] && (
            <span><span className="text-muted">MVP</span>{" "}
              <span className="font-medium text-ink"><PlayerLink pid={String(g.mvp_id ?? "")} name={String(ppl[String(g.mvp_id)])} className="hover:text-accent hover:underline" /></span>
              {dc?.mvp ? <span className="ml-1 text-xs text-muted">本季第 {dc.mvp} 次</span> : null}</span>
          )}
        </Card>
      )}

      {/* 本場焦點 / 賽事資訊 已整併進總覽右卡（GameOverview），此處不重複 */}

      {data.batting.length > 0 && (
        <section className="mb-8">
          <Eyebrow className="mb-3">Box Score・分析</Eyebrow>
          <BoxTabs data={data} />
        </section>
      )}
    </div>
  );
}
