// 單場「本場焦點」純規則（#288 WP-K3 自 `app/games/[sno]/game-summary.ts` 逐字搬移，條件／文字／順序／上限都沒改）。
//
// 單場賽況頁與 `/playoffs` 系列總結區的「逐場焦點」跑**同一個函式**（PRD「抽純規則，不複製條件」）；
// 單場頁經 `game-summary.ts` re-export 取用，呼叫端不變。黃金值釘在 `game-highlights.test.ts`。
// 零 JSX、零 hook、零請求。輸入只需規則實際讀的欄位（`HighlightInput`），單場頁的 `Live` 自然相容；
// 系列總結區的資料來自 `/api/v1/playoffs/highlights` 的欄位投影（後端只投影、⛔ 篩列或判斷）。
//
// ⚠️ 球迷用語（魯閣／中計／煮粥／問天／劇場／萬磁王）只用於焦點標籤，觸發條件早已量化；recap 正式文案禁用暱稱。

import type { StatRow } from "./client.ts";
import { fanNick, teamShort } from "./teams.ts";

export const num = (v: number | string | null | undefined) =>
  (v === null || v === undefined ? 0 : Number(v)) || 0;

export type Highlight = { text: string; team: string | null };

/** 規則實際讀取的欄位（單場頁 `Live` 的子集）。 */
export type HighlightInput = {
  game: StatRow | null;
  scoreboard: StatRow[];
  livelog: StatRow[];
  batting: StatRow[];
  pitching: StatRow[];
  decisions?: Record<string, "W" | "L" | "SV" | "HLD">;
};

/**
 * 本場焦點。門檻原則＝**一季只會出現幾次才配當焦點**。
 * 順序：賽事級（再見／逆轉／延長／和局／合力完封／裁定）→ 稀有成就 → 常見（打者／投手／球速）。
 */
export function buildHighlights(data: HighlightInput, completed: boolean): Highlight[] {
  const g = data.game;
  if (!g) return [];
  const highlights: Highlight[] = [];
  const teamOf = (vht: unknown) =>
    String(vht) === "1" ? String(g.away_team_code ?? "") : String(g.home_team_code ?? "");
  const H = (text: string, team: string | null = null) => highlights.push({ text, team });
  const hs = num(g.home_score);
  const aw = num(g.away_score);

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
      const innings = [...new Set(data.scoreboard.map((r) => num(r.inning_seq)))].sort((x, y) => x - y);
      for (const inn of innings) {
        for (const half of ["1", "2"]) {
          const row = data.scoreboard.find((r) => num(r.inning_seq) === inn
            && String(r.visiting_home_type) === half);
          if (!row) continue;
          if (half === "1") cum.a += num(row.score_cnt);
          else cum.h += num(row.score_cnt);
          maxDef = Math.max(maxDef, winnerHome ? cum.a - cum.h : cum.h - cum.a);
        }
      }
      if (maxDef >= 3) H(`落後 ${maxDef} 分逆轉勝`, String((winnerHome ? g.home_team_code : g.away_team_code) ?? ""));
    }
    const maxInn = Math.max(0, ...data.scoreboard.map((r) => num(r.inning_seq)));
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
    const maxInn0 = Math.max(0, ...data.scoreboard.map((r) => num(r.inning_seq)));
    if (hs !== aw && maxInn0 < 9) H(`${maxInn0} 局裁定比賽`);
  }
  // 賽事級焦點數量錨點：稀有成就（extra）插在其後、常見焦點之前，
  // 確保稀有標籤不被 splice(16) 擠掉。
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
      pv = r.visiting_score != null ? num(r.visiting_score) : pv;
      ph = r.home_score != null ? num(r.home_score) : ph;
    }
    const byHalf = new Map<string, StatRow[]>();
    for (const r of data.livelog) {
      const k = `${r.inning_seq}|${r.visiting_home_type}`;
      if (!byHalf.has(k)) byHalf.set(k, []);
      byHalf.get(k)!.push(r);
    }
    const traps: Record<string, { normal: number; big: number }> =
      { "1": { normal: 0, big: 0 }, "2": { normal: 0, big: 0 } };
    for (const [k, rows] of byHalf) {
      const vht = k.split("|")[1];
      const post = vht === "1" ? "visiting_score" : "home_score";
      const endScore = Math.max(0, ...rows.map((r) => num(r[post])));
      let prevHitter = "", trapped: "big" | "normal" | null = null;
      for (const r of rows) {
        if (r.is_change_player || !r.hitter_acnt) continue;
        if (String(r.hitter_acnt) !== prevHitter) {           // 打席首事件
          prevHitter = String(r.hitter_acnt);
          const loaded = r.first_base && r.second_base && r.third_base;
          if (loaded && endScore - (pre.get(r) ?? 0) === 0) {
            trapped = num(r.out_cnt) === 0 ? "big" : (trapped ?? "normal");
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
      if (num(r.error_cnt) >= 2) {
        const code = teamOf(r.visiting_home_type);
        highlights.push({ text: `${teamShort(code)} 煮粥（${num(r.inning_seq)} 局 ${r.error_cnt} 失誤）`, team: code });
      }
    }
  }
  for (const r of data.batting) {
    const nm = String(r.hitter_name ?? "");
    const tm = teamOf(r.visiting_home_type);
    const hr = num(r.home_runs);
    const h = num(r.hits);
    if (num(r.grand_slam)) H(`${nm} 滿貫砲`, tm);
    else if (hr >= 2) H(`${nm} ${hr} 響砲`, tm);
    // 術語：3安=猛打賞、4安=鐵支、5安+ 直接報數
    if (h === 3) H(`${nm} 猛打賞`, tm);
    else if (h === 4) H(`${nm} 鐵支（單場4安）`, tm);
    else if (h >= 5) H(`${nm} 單場 ${h} 安`, tm);
    if (num(r.rbi) >= 4) H(`${nm} ${r.rbi} 打點`, tm);
    if (num(r.sb) >= 2) H(`${nm} ${r.sb} 次盜壘`, tm);
    // 致勝打點已移至決勝資訊列（勝投/敗投/救援同排），此處不再重複進焦點
  }
  for (const r of data.pitching) {
    const nm = String(r.pitcher_name ?? "");
    const tm = teamOf(r.visiting_home_type);
    const d = (data.decisions ?? {})[String(r.pitcher_acnt)];
    if (r.is_shutout) H(`${nm} 完封`, tm);
    else if (r.is_complete_game) H(`${nm} 完投`, tm);
    if (num(r.so) >= 8) H(`${nm} ${r.so} 次三振`, tm);
    // 問天（網路用語）：優質先發（≥6 局、自責 ≤3）卻吞敗或無關勝負
    const isStarter = String(r.pitcher_acnt) === String(g.away_starter_id)
      || String(r.pitcher_acnt) === String(g.home_starter_id);
    const outs = num(r.inning_pitched_cnt) * 3 + num(r.inning_pitched_div3);
    if (completed && isStarter && outs >= 18 && num(r.earned_runs) <= 3 && d !== "W") {
      H(`${nm} 問天（優質先發${d === "L" ? "吞敗" : "無關勝負"}）`, tm);
    }
    // 劇場（網路用語）：救援成功但過程驚險——讓 ≥2 人上壘或有失分
    if (d === "SV") {
      const runners = num(r.hits) + num(r.bb) + num(r.hbp);
      if (runners >= 2 || num(r.runs) >= 1) H(`${nm} 劇場`, tm);
    }
  }
  // 最速球：≥155 才有焦點價值（日常最速無鑑別度）
  const maxSp = Math.max(0, ...data.pitching.map((r) => num(r.max_speed)));
  if (maxSp >= 155) {
    const fast = data.pitching.find((r) => num(r.max_speed) === maxSp);
    H(`最速球 ${maxSp} km/h`, fast ? teamOf(fast.visiting_home_type) : null);
  }

  const extra = buildRareHighlights(data, completed);
  // 去重：有「單局 N 盜」者，box 級「N 次盜壘」重複、移除
  const inningSteal = new Set(extra.filter((e) => / 單局 \d+ 盜$/.test(e.text)).map((e) => e.text.split(" ")[0]));
  if (inningSteal.size) {
    const dup = (t: string) => { const m = t.match(/^(\S+) \d+ 次盜壘$/); return !!m && inningSteal.has(m[1]); };
    for (let i = highlights.length - 1; i >= 0; i--) if (dup(highlights[i].text)) highlights.splice(i, 1);
  }
  highlights.splice(nGameLevel, 0, ...extra);
  // 上限 16（需求方 #285 批次 F 裁定，原 12）：加入失誤類新標籤後全庫 2018–2026 共 4,509 場 P99＝14、最大 20；
  // 16 時既有標籤 0 擠出（exec-7 cap/cap.json）。
  highlights.splice(16);
  return highlights;
}

/** 焦點擴充（三振／效率／盜壘／上壘家族，全從 livelog+box 客戶端算，2018+）。 */
function buildRareHighlights(data: HighlightInput, completed: boolean): Highlight[] {
  const g = data.game;
  const extra: Highlight[] = [];
  if (!g || !completed || data.livelog.length === 0) return extra;
  const teamOf = (vht: unknown) =>
    String(vht) === "1" ? String(g.away_team_code ?? "") : String(g.home_team_code ?? "");
  const pitchTeam = (half: string) => String((half === "1" ? g.home_team_code : g.away_team_code) ?? "");
  const batTeam = (half: string) => String((half === "1" ? g.away_team_code : g.home_team_code) ?? "");
  const pName = new Map<string, string>();
  for (const r of data.pitching) pName.set(String(r.pitcher_acnt), String(r.pitcher_name ?? ""));
  const hName = new Map<string, string>(), hTeam = new Map<string, string>();
  for (const r of data.batting) {
    hName.set(String(r.hitter_acnt), String(r.hitter_name ?? ""));
    hTeam.set(String(r.hitter_acnt), teamOf(r.visiting_home_type));
  }

  // 逐打席序列（PA 島＝連續同打者非換人事件，末筆為結果）
  type PA = { pitcher: string; hitter: string; inning: number; half: string;
              isK: boolean; onBase: boolean; retired: boolean };
  const paList: PA[] = [];
  let cur: StatRow | null = null;
  const flushPA = () => {
    if (!cur) return;
    const a = String(cur.action_name ?? "");
    const onBase = /安打|全壘打|四壞|敬遠|觸身/.test(a);              // 乾淨上壘（安打/四死）
    const reachedAny = onBase || /失誤|野手選擇|野選|妨礙/.test(a);   // 含失誤/野選上壘
    paList.push({
      pitcher: String(cur.pitcher_acnt ?? ""), hitter: String(cur.hitter_acnt ?? ""),
      inning: num(cur.inning_seq), half: String(cur.visiting_home_type ?? ""),
      isK: /三振/.test(a), onBase, retired: !reachedAny,
    });
    cur = null;
  };
  for (const r of data.livelog) {
    if (r.is_change_player || !r.hitter_acnt) continue;
    if (cur && String((cur as StatRow).hitter_acnt) !== String(r.hitter_acnt)) flushPA();
    cur = r;
  }
  flushPA();
  const pHalf: Record<string, string> = {};
  for (const pa of paList) pHalf[pa.pitcher] = pa.half;

  // 連續三振 ≥5 / 連續解決 ≥6（per pitcher rolling，跨局）
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

  // 單局三振（per pitcher×half ≥3K；寬版含上壘後補 K）
  const inK: Record<string, number> = {};
  for (const pa of paList) if (pa.isK) { const k = `${pa.pitcher}|${pa.inning}|${pa.half}`; inK[k] = (inK[k] ?? 0) + 1; }
  for (const [k, c] of Object.entries(inK)) if (c >= 3) {
    const [p, inn, half] = k.split("|");
    extra.push({ text: `${pName.get(p) ?? ""} ${inn} 局單局 ${c}K`, team: pitchTeam(half) });
  }

  // 全打席上壘（PA ≥4 全上壘＝安打/四死；失誤/野選破壞）
  const paByH: Record<string, PA[]> = {};
  for (const pa of paList) (paByH[pa.hitter] ??= []).push(pa);
  for (const [h, list] of Object.entries(paByH))
    if (list.length >= 4 && list.every((x) => x.onBase))
      extra.push({ text: `${hName.get(h) ?? ""} ${list.length} 打席全上壘`, team: batTeam(list[0].half) });

  // 三球關門（半局內單一投手 ≤3 球完成 3 出局）。球數用 pitch_cnt（投手累計，界內球亦計）。
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
    const key = `${num(r.inning_seq)}|${r.visiting_home_type}`;
    if (key !== curKey) { closeHalf(); curKey = key; }
    const p = String(r.pitcher_acnt ?? ""), pc = num(r.pitch_cnt);
    if (p && pc) curMax[p] = Math.max(curMax[p] ?? 0, pc);
    for (const m of String(r.content ?? "").matchAll(/(\d)人出局/g)) curOut = Math.max(curOut, Number(m[1]));
  }
  closeHalf();

  // 盜壘家族（重用 sabr regex；「盜壘刺」＝失敗不含）
  const sbRe = /([一二三])壘跑者\*?([^\s盜]+?)\s*(?:雙)?盜壘上([二三])壘/g;
  const sbhRe = /三壘跑者\*?([^\s盜]+?)\s*(?:雙)?盜壘回本壘得分/;
  const runSteals: Record<string, { count: number; half: string; name: string }> = {};
  for (const r of data.livelog) {
    const content = String(r.content ?? ""), half = String(r.visiting_home_type ?? ""), inn = num(r.inning_seq);
    let evt = 0, m: RegExpExecArray | null; const re = new RegExp(sbRe);
    while ((m = re.exec(content))) {
      const name = m[2]; evt++;
      (runSteals[`${name}|${inn}|${half}`] ??= { count: 0, half, name }).count++;
    }
    const mh = content.match(sbhRe);
    if (mh) {
      const name = mh[1]; evt++;
      extra.push({ text: `${name} 盜本壘`, team: batTeam(half) });
      (runSteals[`${name}|${inn}|${half}`] ??= { count: 0, half, name }).count++;
    }
    if (evt >= 2) extra.push({ text: "雙盜壘", team: batTeam(half) });   // 同一球 ≥2 跑者盜成功
  }
  for (const v of Object.values(runSteals))
    if (v.count >= 2) extra.push({ text: `${v.name} 單局 ${v.count} 盜`, team: batTeam(v.half) });

  // 先發全員安打（每隊 role_type=先發 全部 ≥1 安）
  for (const side of ["1", "2"]) {
    const st = data.batting.filter((r) => String(r.visiting_home_type) === side && String(r.role_type) === "先發");
    if (st.length >= 9 && st.every((r) => num(r.hits) >= 1)) {
      const code = teamOf(side);
      extra.push({ text: `${teamShort(code)} 先發全員安打`, team: code });
    }
  }

  // 萬磁王（球迷用語：單場觸身 ≥2）。以 content『觸身死球』計（單一事件行）——
  // action_name 是打席層級值、同打席每列重複，數列會爆量（實測 8 觸身誤報）。
  const hbpBy: Record<string, number> = {};
  for (const r of data.livelog) if (/觸身死球/.test(String(r.content ?? ""))) {
    const h = String(r.hitter_acnt ?? ""); hbpBy[h] = (hbpBy[h] ?? 0) + 1;
  }
  for (const [h, c] of Object.entries(hbpBy))
    if (c >= 2) extra.push({ text: `${hName.get(h) ?? ""} 萬磁王（${c} 觸身）`, team: hTeam.get(h) ?? null });

  // #285 批次 F 五個新標籤（道歉全壘打／道歉野球／一棒逆轉／一棒追平／致命失誤）：排在既有稀有組之後。
  extra.push(...buildErrorHighlights(data));
  return extra;
}

// —— #285 批次 F：失誤事件表與五個新標籤（plan-7 r1＋需求方 F-Q1 因果版、F-Q2 全部套用、F-Q3）——————————————
//
// 資料：livelog 敘述（`content`）的具名守位失誤＋記分板逐局 `error_cnt`＋box `errors`。原則：時點或歸屬不明一律不標。
// - 偵測：非換人列的 `content` 以「守位詞＋（接球／漏接／傳X／傳球）失誤」取該列具名守位集合（同列跑者重述去重）；
//   泛稱「因野手失誤進壘」不帶守位，不計入具名。
// - 半局對帳：該半局具名失誤數＝守備方該局 `error_cnt` 才算通過；不等 ⇒ 該半局所有失誤時點與歸屬視為不明。
// - 歸屬：投手＝該列 pitcher_acnt；捕手＝該列 catcher_acnt；其他守位＝守備方 box `errors>0` 且其守位
//   （livelog `defend_station_code`，排除 PH／PR／DH）含該守位者恰一人；某人被歸屬次數超過 box `errors` ⇒ 全改不明。
// - 受影響跑者（致命失誤因果版）：打者因具名失誤上壘＝打者；「X壘跑者NAME 因<守位>…失誤」＝NAME；同列泛稱
//   「X壘跑者NAME 因野手失誤進壘」只在該列恰一個具名失誤時歸給它；失誤未造成進壘（例：界外接球失誤）＝無；
//   其他形狀 ⇒ 不明（該半局不標致命失誤）。
// - 致命失誤：半局對帳通過、守備方半局開始不落後、結束落後；自「由不落後變落後」那一列（含）起各列的失分，
//   每分的得分者姓名都解析得到（`回本壘得分`／全壘打打者）才判；其中至少一人屬某失誤（不晚於其得分列）的
//   受影響跑者 ⇒ 標。
// 全庫可判定比例與 2026 季後黃金值見 #285 exec-7 證據（probe/causal.json、wpf5）。

const ERR_POS: Record<string, string> = {
  投手: "P", 捕手: "C", 一壘手: "1B", 二壘手: "2B", 三壘手: "3B", 游擊手: "SS", 左外野手: "LF", 中外野手: "CF", 右外野手: "RF",
};
const POS_WORD = "(?:投手|捕手|一壘手|二壘手|三壘手|游擊手|左外野手|中外野手|右外野手)";
const ERR_RE = new RegExp(`(${POS_WORD})\\s*(?:接球|漏接|傳\\S{2,5}?(?:傳球)?|傳球)?\\s*失誤`, "g");
const RUNNER_NAMED_RE = new RegExp(`[一二三本]壘跑者\\s*\\*?([^\\s因回上*]+?)\\s*(?:盜壘\\S*?-)?因\\s*${POS_WORD}[^。]*?失誤`);
const RUNNER_GENERIC_RE = /[一二三本]壘跑者\s*\*?([^\s因回上*]+?)\s*(?:盜壘\S*?-)?因野手失誤進壘/;
const SCORER_RE = /跑者\s*\*?([^\s因回上*。]+)[^。]*?回本壘得分/g;
const RBI_RE = /(\d+)分打點/g;

const cleanName = (v: unknown) => String(v ?? "").replace(/\*/g, "").trim();

export type ErrorEvent = {
  /** 在「非換人列」序列中的位置。 */
  rowIndex: number;
  inning: number;
  /** 守備方 visiting_home_type（"1"＝客隊）。 */
  fieldingSide: string;
  position: string;
  /** 失誤者；半局對帳不過、捕手列缺 catcher_acnt、守位候選不唯一、超過 box 數 ⇒ null。 */
  playerAcnt: string | null;
  /** 受此列失誤影響（上壘或進壘）的跑者姓名；null＝不明。 */
  affected: Set<string> | null;
};

/** 失誤事件表（純函式）。回傳事件與「半局（`${inning}|${fieldingSide}`）→ 是否對帳通過」。 */
export function errorEvents(data: HighlightInput): { events: ErrorEvent[]; halfOk: Map<string, boolean>; rows: StatRow[] } {
  const rows = data.livelog.filter((r) => !r.is_change_player);
  const events: ErrorEvent[] = [];
  const named = new Map<string, number>();
  rows.forEach((r, i) => {
    const content = String(r.content ?? "");
    const ps = new Set<string>();
    for (const m of content.matchAll(ERR_RE)) ps.add(ERR_POS[m[1]]);
    if (!ps.size) return;
    const fieldingSide = String(r.visiting_home_type) === "1" ? "2" : "1";
    const inning = num(r.inning_seq);
    const key = `${inning}|${fieldingSide}`;
    named.set(key, (named.get(key) ?? 0) + ps.size);
    let affected: Set<string> | null = new Set<string>();
    const generic: string[] = [];
    for (const sentence of content.split("。")) {
      if (!sentence.includes("失誤")) continue;
      const hasNamed = new RegExp(ERR_RE.source).test(sentence);
      if (!sentence.includes("跑者") && hasNamed && /失誤(?:上[一二三]壘|上壘)/.test(sentence)) {
        affected.add(cleanName(r.hitter_name));              // 打者因具名失誤上壘
        continue;
      }
      const mn = sentence.match(RUNNER_NAMED_RE);
      if (mn) { affected.add(cleanName(mn[1])); continue; }
      const mg = sentence.match(RUNNER_GENERIC_RE);
      if (mg) { generic.push(cleanName(mg[1])); continue; }
      if (hasNamed && !/失誤(?:上|回|進壘)/.test(sentence)) continue;   // 失誤未造成進壘
      affected = null;
      break;
    }
    if (affected && generic.length) {
      if (ps.size === 1) for (const n of generic) affected.add(n);
      else affected = null;
    }
    for (const position of ps) {
      events.push({ rowIndex: i, inning, fieldingSide, position, playerAcnt: null,
        affected: affected ? new Set(affected) : null });
    }
  });
  // 半局對帳（記分板 vht＝該隊；該隊守備時犯的失誤）
  const sb = new Map<string, number>();
  for (const r of data.scoreboard) {
    const key = `${num(r.inning_seq)}|${String(r.visiting_home_type)}`;
    sb.set(key, (sb.get(key) ?? 0) + num(r.error_cnt));
  }
  const halfOk = new Map<string, boolean>();
  for (const [key, n] of named) halfOk.set(key, n === (sb.get(key) ?? 0));
  // 歸屬
  const posOf = new Map<string, Set<string>>();
  for (const r of data.livelog) {
    if (r.is_change_player || !r.hitter_acnt) continue;
    const pos = String(r.defend_station_code ?? "");
    if (!pos || pos === "PH" || pos === "PR" || pos === "DH") continue;
    const k = String(r.hitter_acnt);
    if (!posOf.has(k)) posOf.set(k, new Set());
    posOf.get(k)!.add(pos);
  }
  const boxErrors = new Map<string, { side: string; errors: number }>();
  for (const row of data.batting) {
    if (row.errors === undefined || row.errors === null) continue;
    boxErrors.set(String(row.hitter_acnt), { side: String(row.visiting_home_type), errors: num(row.errors) });
  }
  const counted = new Map<string, number>();
  for (const ev of events) {
    if (!halfOk.get(`${ev.inning}|${ev.fieldingSide}`)) continue;
    const row = rows[ev.rowIndex];
    if (ev.position === "P") ev.playerAcnt = row.pitcher_acnt ? String(row.pitcher_acnt) : null;
    else if (ev.position === "C") ev.playerAcnt = row.catcher_acnt ? String(row.catcher_acnt) : null;
    else {
      const cand = [...boxErrors].filter(([acnt, b]) => b.side === ev.fieldingSide && b.errors > 0
        && (posOf.get(acnt)?.has(ev.position) ?? false)).map(([acnt]) => acnt);
      ev.playerAcnt = cand.length === 1 ? cand[0] : null;
      if (ev.playerAcnt) counted.set(ev.playerAcnt, (counted.get(ev.playerAcnt) ?? 0) + 1);
    }
  }
  for (const ev of events) {
    if (ev.playerAcnt && ev.position !== "P" && ev.position !== "C"
        && (counted.get(ev.playerAcnt) ?? 0) > (boxErrors.get(ev.playerAcnt)?.errors ?? 0)) ev.playerAcnt = null;
  }
  return { events, halfOk, rows };
}

/** 五個新標籤（純函式；呼叫端已確認完賽）。 */
function buildErrorHighlights(data: HighlightInput): Highlight[] {
  const g = data.game;
  if (!g || data.livelog.length === 0) return [];
  const out: { at: number; h: Highlight }[] = [];
  const teamOfSide = (side: string) => String((side === "1" ? g.away_team_code : g.home_team_code) ?? "");
  const { events, halfOk, rows } = errorEvents(data);
  // 事件前／後比分（比分欄＝事件後；null 延用上一列）
  const pre: [number, number][] = [], post: [number, number][] = [];
  let pv = 0, ph = 0;
  for (const r of rows) {
    pre.push([pv, ph]);
    pv = r.visiting_score != null ? num(r.visiting_score) : pv;
    ph = r.home_score != null ? num(r.home_score) : ph;
    post.push([pv, ph]);
  }
  const lead = ([v, h]: [number, number], side: string) => (side === "1" ? v - h : h - v);

  // 打席島（連續同打者、非換人）
  const islands: number[][] = [];
  let curIsland: number[] = [];
  rows.forEach((r, i) => {
    if (!r.hitter_acnt) return;
    if (curIsland.length && String(rows[curIsland[0]].hitter_acnt) !== String(r.hitter_acnt)) {
      islands.push(curIsland); curIsland = [];
    }
    curIsland.push(i);
  });
  if (curIsland.length) islands.push(curIsland);

  for (const isl of islands) {
    const f = isl[0], l = isl[isl.length - 1];
    const r = rows[l];
    const side = String(r.visiting_home_type ?? "");
    const team = teamOfSide(side);
    const hitter = String(r.hitter_acnt ?? "");
    const name = cleanName(r.hitter_name);
    const hr = String(r.action_name ?? "").includes("全壘打");
    const before = lead(pre[f], side), after = lead(post[l], side);
    // 道歉全壘打／道歉野球（F-Q3：全壘打只出道歉全壘打）
    const owed = events.some((ev) => ev.playerAcnt === hitter && ev.rowIndex < f);
    if (owed) {
      let rbi = 0;
      for (const i of isl) for (const m of String(rows[i].content ?? "").matchAll(RBI_RE)) rbi = Math.max(rbi, Number(m[1]));
      if (hr) out.push({ at: l, h: { text: `${name} 道歉全壘打`, team } });
      else if (rbi >= 1) out.push({ at: l, h: { text: `${name} 道歉野球`, team } });
    }
    // 一棒逆轉／一棒追平
    if (hr && before < 0 && after > 0) out.push({ at: l, h: { text: `${name} 一棒逆轉`, team } });
    if (hr && before < 0 && after === 0) out.push({ at: l, h: { text: `${name} 一棒追平`, team } });
  }

  // 致命失誤（因果版）
  const halves = new Set(events.map((ev) => `${ev.inning}|${ev.fieldingSide}`));
  for (const key of halves) {
    if (!halfOk.get(key)) continue;
    const [innS, fv] = key.split("|");
    const inning = Number(innS);
    const hevs = events.filter((ev) => ev.inning === inning && ev.fieldingSide === fv);
    if (hevs.some((ev) => ev.affected === null)) continue;
    const idx = rows.map((r, i) => (num(r.inning_seq) === inning && String(r.visiting_home_type) !== fv ? i : -1))
      .filter((i) => i >= 0);
    if (!idx.length) continue;
    if (!(lead(pre[idx[0]], fv) >= 0 && lead(post[idx[idx.length - 1]], fv) < 0)) continue;
    let behind = -1;
    for (const i of idx) if (lead(pre[i], fv) >= 0 && lead(post[i], fv) < 0) behind = i;
    if (behind < 0) continue;
    let determinable = true, hit = false;
    for (const i of idx) {
      if (i < behind) continue;
      const r = rows[i];
      const runs = lead(pre[i], fv) - lead(post[i], fv);
      const scorers = [...String(r.content ?? "").matchAll(SCORER_RE)].map((m) => cleanName(m[1]));
      if (String(r.content ?? "").includes("全壘打") && String(r.action_name ?? "").includes("全壘打")) scorers.push(cleanName(r.hitter_name));
      if (runs !== scorers.length) { determinable = false; break; }
      if (scorers.some((n) => hevs.some((ev) => ev.rowIndex <= i && ev.affected!.has(n)))) hit = true;
    }
    if (determinable && hit) {
      const code = teamOfSide(fv);
      out.push({ at: idx[idx.length - 1], h: { text: `${teamShort(code)} 致命失誤（${inning} 局）`, team: code } });
    }
  }
  return out.sort((a, b) => a.at - b.at).map((o) => o.h);
}
