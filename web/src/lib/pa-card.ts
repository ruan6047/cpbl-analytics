// UX-GAME-PA1：逐打席卡片的**資料組裝**（純函式，與呈現分離）。
//
// 一張逐打席卡需要的局面脈絡（壘包／出局／分差）在 canonical 打席事實流裡都有，但賽況頁
// 的逐打席在**事實流缺席時**必須照常運作（`buildPaGroups` 的「換底不換臉」保證）。故本
// 模組定義單一優先序，讓兩條路徑產出同一種卡：
//
//   1. **canonical 打席事實流優先**（`PaFact`）：壘況／出局／打席前比分／ΔRE24／官方結果
//      一律以事實流為準——它是 SSoT，且比分已修正「事件後快照」的陷阱。
//   2. **退回 livelog 首事件**：事實流缺席（來源修正／暫態）時，以該打席**首事件**的
//      `out_cnt`／壘位欄作打席前狀態——與已上線的 `/winprob` 逐打席取值同一套慣例，
//      兩處對照不打架；比分則取首事件**之前**的累計比分（livelog 比分欄是事件後值）。
//
// 缺值一律往下傳 null，由呈現層顯示「—」；**不以 0 冒充**。

import { halfLabel, personName, type PaFact } from "./game-facts.ts";

/** 逐打席只用得到 livelog 的這幾欄（與 `buildPaGroups` 同樣採最小依賴）。 */
export type PaCardEvent = {
  inning_seq?: unknown;
  visiting_home_type?: unknown;
  out_cnt?: unknown;
  first_base?: unknown;
  second_base?: unknown;
  third_base?: unknown;
  action_name?: unknown;
  content?: unknown;
  main_event_no?: unknown;
};

/** 事件流逐列的「事件後」比分（`runningScore[i]`）。 */
export type RunningScore = { runs: number; away: number; home: number };

export type PaCardVM = {
  inning: number | null;
  half: string | null;
  outsBefore: number | null;
  basesBefore: string[];
  margin: string;
  garbageTime: boolean;
  resultAction: string | null;
  runs: number | null;
  scoreAfter: { away: number; home: number } | null;
  deltaRe24: number | null;
};

const numOrNull = (v: unknown): number | null => {
  if (v === null || v === undefined || v === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
};

/** livelog 壘位欄（有人＝truthy）→ 事實流同款的 `["1","3"]` 形式。 */
export function basesFromEvent(ev: PaCardEvent | undefined): string[] {
  if (!ev) return [];
  const out: string[] = [];
  if (ev.first_base) out.push("1");
  if (ev.second_base) out.push("2");
  if (ev.third_base) out.push("3");
  return out;
}

/** 打席前分差文字（與關鍵打席卡同一套用語）。 */
export function marginTextOf(away: number | null, home: number | null): string {
  if (away === null || home === null) return "";
  if (away === home) return "平手";
  return `${Math.max(away, home)}–${Math.min(away, home)}`;
}

/**
 * 組出一張逐打席卡所需的欄位。
 *
 * @param fact       canonical 打席（缺席時走 livelog 退路）
 * @param first      該打席的**首事件**
 * @param last       該打席的**末事件**（官方結果取自此列）
 * @param preScore   首事件**之前**的累計比分（`runningScore[firstIdx - 1]`；首列為 null）
 * @param scoreAfter 該打席最後一個得分事件的事件後比分（無得分為 null）
 * @param runs       該打席進帳分數（無得分為 0／null）
 */
export function buildPaCardVM(
  fact: PaFact | null | undefined,
  first: PaCardEvent | undefined,
  last: PaCardEvent | undefined,
  preScore: RunningScore | null,
  scoreAfter: { away: number; home: number } | null,
  runs: number | null,
): PaCardVM {
  const ready = fact?.state === "ready";
  const awayBefore = ready ? fact!.away_score_before : (preScore?.away ?? null);
  const homeBefore = ready ? fact!.home_score_before : (preScore?.home ?? null);
  const resultFromLog = String(last?.action_name ?? "").trim();
  return {
    inning: ready ? fact!.inning : numOrNull(first?.inning_seq),
    half: ready ? fact!.half : (first?.visiting_home_type != null
      ? String(first.visiting_home_type) : null),
    // `out_cnt` 是**打席前**出局數（`docs/reference/GLOSSARY.md`），可直接用作首事件的局面
    outsBefore: ready ? fact!.outs_before : numOrNull(first?.out_cnt),
    basesBefore: ready ? (fact!.bases_before ?? []) : basesFromEvent(first),
    margin: marginTextOf(awayBefore, homeBefore),
    garbageTime: ready ? fact!.garbage_time : false,
    resultAction: (ready ? fact!.result_action : null) || resultFromLog || null,
    runs: ready ? fact!.runs_on_play : runs,
    scoreAfter: ready && fact!.away_score_after !== null && fact!.home_score_after !== null
      ? { away: fact!.away_score_after, home: fact!.home_score_after }
      : scoreAfter,
    // ΔRE24 只在 canonical 打席可靠時才有（退路不自行推算）
    deltaRe24: ready ? fact!.delta_re24 : null,
  };
}

/** 合體版比分列（`PaScoreLine`）的資料；非得分打席為 null。 */
export type PaScoreLineData = {
  /** 該打席**得分後**的比分（`score_after`；不由前值＋進帳推算）。 */
  away: number;
  home: number;
  /** 該打席進帳分數（> 0）。 */
  runs: number;
  /**
   * `(+N)` 掛在哪一側。進帳一定屬於**進攻方**：上半局（`half==="1"`）＝客隊、
   * 下半局＝主隊。半局不明時回 null，由呈現層把 `(+N)` 放在比分之後而不亂掛一側。
   */
  side: "away" | "home" | null;
};

/** 得分打席 → 比分列資料；無得分或比分缺值時回 null（呈現層據此不渲染該列）。 */
export function paScoreLineOf(
  pa: { scoreAfter: { away: number; home: number } | null; runs: number | null; half: string | null },
): PaScoreLineData | null {
  if (!pa.scoreAfter || !pa.runs || pa.runs <= 0) return null;
  const half = String(pa.half);
  return {
    away: pa.scoreAfter.away,
    home: pa.scoreAfter.home,
    runs: pa.runs,
    side: half === "1" ? "away" : half === "2" ? "home" : null,
  };
}

/** 卡片的無障礙標籤（螢幕閱讀器不看壘包圖示，須有文字替代）。 */
export function paCardLabel(vm: PaCardVM, hitterName: string, swingText: string): string {
  const bases = vm.basesBefore.length === 0 ? "壘上無人"
    : vm.basesBefore.length === 3 ? "滿壘"
    : `${vm.basesBefore.map((b) => (b === "1" ? "一" : b === "2" ? "二" : "三")).join("、")}壘有人`;
  const situation = `${vm.inning ?? "—"} 局${halfLabel(vm.half)}　${vm.outsBefore ?? "—"} 出局　${bases}`;
  return `${situation}，${hitterName} ${vm.resultAction ?? ""}${swingText}`;
}

/** 事實流的打者姓名優先（記錄歸屬依規則 9.15(b)），缺席時用近似分組的姓名。 */
export const paCardHitterName = (fact: PaFact | null | undefined, fallback: string): string =>
  (fact ? personName(fact.hitter) : "") || fallback;
