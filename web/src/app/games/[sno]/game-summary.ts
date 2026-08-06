// UX-GAME-RECAP1 重構：把原本內嵌在 `game-live-page.tsx`（721 行）的**純計算**抽出。
//
// 本檔零 JSX、零 hook、零請求——只吃 `Live` payload 回傳資料結構，故可單元測試，
// 也讓頁面殼回到「載入 + 三態路由」的職責。行為與抽出前**逐項等價**（只是搬家）。
//
// 產出三組：
//   * `buildHighlights`：本場焦點（賽事級 → 稀有成就 → 常見；含已量化的球迷用語）
//   * `buildDecisions`：決勝資訊（先發／勝敗投／中繼／救援／致勝打點）與 MVP 成績行
//   * `buildGameInfo`：賽事資訊（天氣／觀眾／時長／延賽備註）——裁判列含連結，留在頁面層
//
// ⚠️ 球迷用語（魯閣／中計／煮粥／問天／劇場…）**只用於賽況頁焦點區**，其觸發條件早已
// 量化；recap 的正式文案（結論行事實句）**禁用暱稱**，由後端 `pa_facts` 負責。

import type { Live } from "@/components/game-board";
import type { StatRow } from "@/lib/client";
import { fanNick, teamShort } from "@/lib/teams";

export const num = (v: number | string | null | undefined) =>
  (v === null || v === undefined ? 0 : Number(v)) || 0;

export type Highlight = { text: string; team: string | null };
export type DecItem = { label: string; value: string; note?: string; pid?: string };
export type MvpLine = { name: string; line: string; count?: number | null; pid?: string };

const ipTxt = (r: StatRow) => {
  const whole = num(r.inning_pitched_cnt);
  const third = num(r.inning_pitched_div3);
  return third ? `${whole}.${third}` : String(whole);
};

/**
 * 本場焦點。門檻原則＝**一季只會出現幾次才配當焦點**。
 * 順序：賽事級（再見／逆轉／延長／和局／合力完封／裁定）→ 稀有成就 → 常見（打者／投手／球速）。
 */
export function buildHighlights(data: Live, completed: boolean): Highlight[] {
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
  // 確保稀有標籤不被 splice(12) 擠掉。
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
  highlights.splice(12);
  return highlights;
}

/** 焦點擴充（三振／效率／盜壘／上壘家族，全從 livelog+box 客戶端算，2018+）。 */
function buildRareHighlights(data: Live, completed: boolean): Highlight[] {
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

  return extra;
}

/** 決勝資訊 ＋ MVP 成績行（box score 慣例「本季第 N 勝/敗/救援/中繼/次 MVP」，含本場）。 */
export function buildDecisions(data: Live, completed: boolean): {
  items: DecItem[]; mvp: MvpLine | null;
} {
  const g = data.game;
  if (!g) return { items: [], mvp: null };
  const dc = data.decision_counts;
  const ppl = data.people;

  // MVP 的 box 成績行：優先用 `is_mvp` 旗標；旗標缺席時退回以 `game.mvp_id` 對位。
  //
  // 為什麼需要退路：`is_mvp` 是主站 box 專有旗標，而 `applyLiveSnapshot` 在有 live
  // snapshot 時會把 box 陣列換成 stats 站的列，且**只在 DB 尚無決勝資料時**才回補旗標
  // （`fromDb` 分支）。於是「DB 已有決勝 ＋ snapshot 仍在 48h TTL 內」的窗口裡，旗標
  // 兩邊都沒有，MVP 的成績行與本季次數會整塊消失。以 mvp_id 對位可涵蓋兩條路徑。
  const mvpId = String(g.mvp_id ?? "");
  const mvpBat = data.batting.find((r) => r.is_mvp)
    ?? (mvpId ? data.batting.find((r) => String(r.hitter_acnt) === mvpId) : undefined);
  const mvpPit = data.pitching.find((r) => r.is_mvp)
    ?? (mvpId ? data.pitching.find((r) => String(r.pitcher_acnt) === mvpId) : undefined);
  let mvp: MvpLine | null = null;
  if (mvpBat) {
    const parts = [`${num(mvpBat.at_bats)} 打數 ${num(mvpBat.hits)} 安`];
    if (num(mvpBat.home_runs)) parts.push(`${mvpBat.home_runs} 轟`);
    if (num(mvpBat.rbi)) parts.push(`${mvpBat.rbi} 打點`);
    if (num(mvpBat.runs)) parts.push(`${mvpBat.runs} 得分`);
    if (num(mvpBat.sb)) parts.push(`${mvpBat.sb} 盜`);
    mvp = { name: String(mvpBat.hitter_name ?? ""), line: parts.join("・"),
            count: dc?.mvp, pid: String(mvpBat.hitter_acnt ?? "") };
  } else if (mvpPit) {
    const parts = [`${ipTxt(mvpPit)} 局`, `${num(mvpPit.so)}K`, `失 ${num(mvpPit.runs)} 分`];
    if (num(mvpPit.bb) === 0) parts.push("無保送");
    mvp = { name: String(mvpPit.pitcher_name ?? ""), line: parts.join("・"),
            count: dc?.mvp, pid: String(mvpPit.pitcher_acnt ?? "") };
  }

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
    .filter((r) => num(r.gw_rbi) > 0)
    .map((r) => String(r.hitter_name ?? ""))
    .filter(Boolean).join("、");

  const starterItems: DecItem[] = ([
    { label: "先發(客)", value: ppl[String(g.away_starter_id)], pid: String(g.away_starter_id ?? "") },
    { label: "先發(主)", value: ppl[String(g.home_starter_id)], pid: String(g.home_starter_id ?? "") },
  ] as DecItem[]).filter((d) => d.value);
  const resultItems: DecItem[] = ([
    { label: "勝投", value: ppl[String(g.winning_pitcher_id)], note: dc?.win ? `第${dc.win}勝` : undefined, pid: String(g.winning_pitcher_id ?? "") },
    { label: "敗投", value: ppl[String(g.losing_pitcher_id)], note: dc?.loss ? `第${dc.loss}敗` : undefined, pid: String(g.losing_pitcher_id ?? "") },
    { label: "救援", value: ppl[String(g.closer_id)], note: dc?.save ? `第${dc.save}救援` : undefined, pid: String(g.closer_id ?? "") },
    { label: "中繼", value: holdNames || undefined, note: holdNote },   // HLD 為官方 relief_point（中繼點）
    { label: "致勝打點", value: gwRbiNames || undefined },
  ] as DecItem[]).filter((d) => d.value);

  return {
    items: completed ? [...starterItems, ...resultItems] : starterItems,
    mvp: completed ? mvp : null,
  };
}

/** 延賽／保留說明文字；無延賽回空字串。 */
export function delayNoteOf(g: StatRow): string {
  if (!g.delay_kind) return "";
  const md = (s: unknown) => { const p = String(s ?? "").slice(5).split("-"); return p.length === 2 ? `${+p[0]}/${+p[1]}` : ""; };
  const orig = md(g.orig_date), played = md(g.game_date);
  const done = num(g.present_status) === 1 && (num(g.home_score) + num(g.away_score)) > 0;
  return g.delay_kind === "保留"
    ? `原 ${orig} 開賽${done ? `，${played} 續賽完成` : "，擇期續賽"}`
    : `原定 ${orig}${done && played !== orig ? `，${played} 補賽` : "，擇期補賽"}`;
}

/** 賽事資訊的「概況」列（天氣／觀眾／時長）；無資料回 null。 */
export function summaryLine(detail: StatRow | null): string | null {
  if (!detail) return null;
  const parts: string[] = [];
  const wx = String(detail.weather_desc ?? "");
  if (wx) {
    const cond = wx.split("。")[0] ?? "";
    const temp = wx.match(/攝氏(\d+)至(\d+)度/);
    const icon = /雷|雨/.test(cond) ? "🌧️" : /多雲/.test(cond) ? "⛅"
      : /陰/.test(cond) ? "☁️" : /晴/.test(cond) ? "☀️" : "🌡️";
    parts.push(`${icon} ${cond}${temp ? ` ${temp[1]}–${temp[2]}°C` : ""}`);
  }
  if (detail.attendance) parts.push(`觀眾 ${Number(detail.attendance).toLocaleString()} 人`);
  if (detail.game_time) parts.push(`時長 ${String(detail.game_time)}`);
  return parts.length ? parts.join("・") : null;
}

/** 生涯里程碑 → 帶隊色的 chip 清單（球員名 → visiting_home_type → 隊碼）。 */
export function buildMilestoneChips(
  data: Live, milestones: { player: string; text: string }[],
): Highlight[] {
  const g = data.game;
  const nameTeam = new Map<string, string>();
  const teamOf = (vht: unknown) =>
    String(vht) === "1" ? String(g?.away_team_code ?? "") : String(g?.home_team_code ?? "");
  for (const r of data.pitching) {
    const nm = String(r.pitcher_name ?? "");
    if (nm) nameTeam.set(nm, teamOf(r.visiting_home_type));
  }
  for (const r of data.batting) {
    const nm = String(r.hitter_name ?? "");
    if (nm) nameTeam.set(nm, teamOf(r.visiting_home_type));
  }
  return milestones.map((m) => ({
    text: `🏆 ${m.player} ${m.text}`,
    team: nameTeam.get(m.player) ?? null,
  }));
}
