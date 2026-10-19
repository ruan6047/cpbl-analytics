// #337 機械檢查 CLI（plan-1 WP3）：同一場「單場頁本場焦點」與「/playoffs 逐場焦點」是否逐字一致。
//
// 用法（在 web/ 下）：
//   node --no-warnings --experimental-strip-types scripts/check-highlights-parity.ts --season 2026 --series C
//   選項：--base <url>（預設 https://cpbl.ruan-ruan.com）、--json（輸出完整比對 JSON）
//
// 流程：GET highlights → 逐場循序 GET /live → 再 GET 一次 highlights。兩次 context_version 不同＝資料正在更新，
// 本次不判（rc=2），請隔 ≥1 分鐘重跑；⛔ 本程式內不自動重試（單次最多 系列場數＋2 個 GET）。
// 判定用頁面實際的函式（src/lib/highlights-parity.ts），不另寫規則。只做 GET；⛔ 不打 stats.cpbl.com.tw。
//
// 結束碼：0＝全部一致；1＝至少一場不一致（印差異）；2＝資料移動中或讀取失敗（不判）；64＝參數錯誤。

import { checkSeriesParity, type GameParity } from "../src/lib/highlights-parity.ts";
import type { LiveApiResponse } from "../src/lib/live-game.ts";
import { highlightsPath, type HighlightsPayload } from "../src/lib/playoffs-series-highlights.ts";

type Args = { season: number; series: "C" | "E"; base: string; json: boolean };

function parseArgs(argv: string[]): Args | string {
  const get = (name: string) => {
    const i = argv.indexOf(name);
    return i >= 0 ? argv[i + 1] : undefined;
  };
  const season = Number(get("--season"));
  const series = get("--series");
  const base = (get("--base") ?? "https://cpbl.ruan-ruan.com").replace(/\/+$/, "");
  if (!Number.isInteger(season) || season < 2026) return "--season 必須是 2026 以後的年份";
  if (series !== "C" && series !== "E") return "--series 必須是 C 或 E";
  let host: string;
  try {
    host = new URL(base).hostname;
  } catch {
    return `--base 不是合法 URL：${base}`;
  }
  if (host === "stats.cpbl.com.tw") return "⛔ 不打 stats.cpbl.com.tw";
  return { season, series, base, json: argv.includes("--json") };
}

let requests = 0;
async function getJson<T>(url: string): Promise<T> {
  requests += 1;
  const res = await fetch(url, {
    headers: { accept: "application/json", "user-agent": "cpbl-analytics highlights-parity check (#337)" },
    signal: AbortSignal.timeout(20_000),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status} ${url}`);
  return res.json() as Promise<T>;
}

const side = (s: GameParity["page"]) => (s.status === "ok" ? s.tags.join("、") || "（無標籤）" : `〔${s.status}〕`);

async function main(): Promise<number> {
  const args = parseArgs(process.argv.slice(2));
  if (typeof args === "string") {
    console.error(args);
    return 64;
  }
  const { season, series, base } = args;
  const hlUrl = `${base}${highlightsPath(season, series)}`;
  const startedAt = new Date().toISOString();
  let first: HighlightsPayload;
  let second: HighlightsPayload;
  const lives = new Map<number, LiveApiResponse>();
  try {
    first = await getJson<HighlightsPayload>(hlUrl);
    if (first.contract !== "playoffs-highlights/v1") throw new Error(`未知 contract：${String(first.contract)}`);
    for (const g of first.games) {
      const sno = g.game_key.game_sno;
      lives.set(sno, await getJson<LiveApiResponse>(
        `${base}/api/v1/games/${sno}/live?kind_code=${g.game_key.kind_code}&season=${g.game_key.year}`));
    }
    second = await getJson<HighlightsPayload>(hlUrl);
  } catch (e) {
    console.error(`讀取失敗（不判）：${e instanceof Error ? e.message : String(e)}`);
    return 2;
  }
  const header = `[highlights-parity] ${base} season=${season} series=${series} started=${startedAt} requests=${requests}`;
  if (first.context_version !== second.context_version) {
    console.log(header);
    console.log(`context_version 前後不同（${first.context_version} → ${second.context_version}）：資料更新中，本次不判（rc=2）`);
    return 2;
  }
  const result = checkSeriesParity(first, lives);
  console.log(header);
  console.log(`context_version=${first.context_version} games=${result.games.length}`);
  for (const g of result.games) {
    const live = lives.get(g.game_sno)?.live_snapshot;
    const snap = live ? `snapshot=${live.phase}` : "snapshot=null";
    console.log(`${g.equal ? "OK  " : "DIFF"} ${g.key} ${g.label} ${snap}`);
    console.log(`     單場頁   ${side(g.page)}`);
    if (!g.equal) console.log(`     /playoffs ${side(g.playoffs)}`);
  }
  if (args.json) console.log(JSON.stringify(result, null, 1));
  if (result.games.length === 0) console.log("（該系列尚無已完賽場，沒有可比對的場次）");
  console.log(result.ok ? "結果：全部一致（rc=0）" : "結果：有不一致（rc=1）");
  return result.ok ? 0 : 1;
}

process.exitCode = await main();
