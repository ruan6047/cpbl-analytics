// 「如果現在對決」單一打席結果分布的呈現層判定（UX-PA-SIM-MATCHUP1）。
//
// T4 紅線（統計／ML）：本檔只做「能不能顯示、要顯示哪一種退化」的判定，
// 所有統計計算（經驗貝氏收縮、轉移核、勝率）都在 API／artifact 完成，
// 前端不得重做，也不得在任何退化態自行生成替代機率（卡片驗收條件 3）。
//
// 承接 ml-sim1-review 的兩條殘餘風險（該報告 §殘餘風險 1–3）：
//   1. weighted-WP 相對現行場中 WP 的改善量 0.000092 在雜訊水準
//      → 文案不得宣稱整場勝負預測提升。
//   2. probability_interval_90 是常態近似的模型敏感度範圍
//      → 不得稱為信賴區間。
import type { Kind, PaOutcomeKey, PaSimOk, PaSimResponse, PaState } from "./api";

/** 機率總和對帳容差：七種結果互斥且窮盡，總和必為 1（浮點誤差內）。 */
export const SUM_TOLERANCE = 1e-6;

/** pa_sim 的訓練母體與轉移核僅限一軍例行賽。 */
export const SUPPORTED_KIND: Kind = "A";

/**
 * 面板狀態。四種退化各自獨立（驗收條件 3），不得合併為泛用「資料不足」：
 * - unsupported：查詢賽事類型不在模擬母體內（C／E 沒有對應轉移核）
 * - artifact_missing：模型檔未建置或損毀（API available=false 且 reason 指 artifact）
 * - unavailable：API 明示的其他不可用原因（如無法定位打席、cutoff 不符）
 * - api_error：請求本身失敗（非 200／網路錯誤）
 * 另兩個 fail-closed 態：
 * - league_fallback：任一側在模型中沒有打席樣本，估計會退化為聯盟基準
 *   → 不得當成「這兩人」的機率呈現，故不顯示任何機率
 * - invariant_failed：回應自我矛盾（缺結果鍵或機率總和未過對帳）
 */
export type PaSimState =
  | { kind: "ok"; data: PaSimOk }
  | { kind: "unsupported"; kindCode: Kind }
  | { kind: "league_fallback"; side: "hitter" | "pitcher" | "both" }
  | { kind: "invariant_failed"; sum: number | null; missing: PaOutcomeKey[] }
  | { kind: "artifact_missing"; reason: string }
  | { kind: "unavailable"; reason: string }
  | { kind: "api_error" };

/** 七種互斥結果的固定顯示序（依上壘價值，不依機率大小重排）。 */
export const OUT_KEYS: readonly PaOutcomeKey[] = ["K", "BIP_OUT"];
export const REACH_KEYS: readonly PaOutcomeKey[] = [
  "BB_HBP",
  "1B",
  "XBH",
  "HR",
  "OTHER_REACH",
];
export const ALL_OUTCOME_KEYS: readonly PaOutcomeKey[] = [...OUT_KEYS, ...REACH_KEYS];

export const PA_OUTCOME_LABEL: Record<PaOutcomeKey, string> = {
  K: "三振",
  BIP_OUT: "擊出後出局",
  BB_HBP: "四壞／觸身",
  "1B": "一壘安打",
  XBH: "二／三壘安打",
  HR: "全壘打",
  OTHER_REACH: "其他上壘",
};

export const PA_OUTCOME_HINT: Record<PaOutcomeKey, string> = {
  K: "投手三振出局。",
  BIP_OUT: "打進場內後被接殺、封殺或觸殺出局（含滾地、飛球）。",
  BB_HBP: "四壞球或觸身球保送上壘。",
  "1B": "一壘安打。",
  XBH: "二壘安打或三壘安打（不含全壘打）。",
  HR: "全壘打。",
  OTHER_REACH: "其他上壘方式（如失誤、妨礙、不死三振上壘）。",
};

/** 六種非 ok 態的標題與說明；標題與說明皆不得互相共用（blueprint §8.1）。 */
export const PA_SIM_COPY = {
  unsupported: {
    title: "此賽事類型沒有可用的打席模擬母體",
    body:
      "單一打席模擬的估計與狀態轉移都以一軍例行賽的逐打席資料建立，" +
      "季後挑戰賽與總冠軍賽沒有對應母體，因此不輸出任何機率。" +
      "把上方賽事類型切回一軍例行賽即可使用；歷史實績查詢不受影響。",
  },
  league_fallback: {
    title: "缺少可估計的個人打席樣本",
    body:
      "這組對決中至少有一方在模擬母體內沒有可用的打席紀錄，" +
      "估計會退化成聯盟整體分布——那不是這兩位球員的機率，因此不顯示。" +
      "不以聯盟平均代替個人估計。",
  },
  invariant_failed: {
    title: "回應未通過結果分布對帳",
    body:
      "七種結果互斥且窮盡，機率總和必須為 1；本次回應缺少結果項或總和不符，" +
      "屬資料異常，因此不呈現任何數字，也不做局部顯示。",
  },
  artifact_missing: {
    title: "模擬模型檔尚未就緒",
    body:
      "打席模擬需要離線訓練產生的模型檔；目前這份檔案未建置或無法載入。" +
      "此為模型資產狀態，不是這組對決缺資料——歷史實績查詢不受影響。",
  },
  unavailable: {
    title: "此組合目前無法模擬",
    body:
      "服務已回報明確原因（見下方說明），在原因解除前不輸出機率；" +
      "不改用其他情境或其他球員的數字替代。",
  },
  api_error: {
    title: "模擬服務暫時無法連線",
    body:
      "請求未成功送達或回應無法解析，屬連線／服務層問題，" +
      "不是模型結論。可稍後重試；歷史實績查詢不受影響。",
  },
} as const;

/** 面板固定揭露文案（紅線：不得改寫成預測整場或信賴區間語氣）。 */
export const PA_SIM_DISCLOSURE = {
  scopeNote:
    "此模擬只回答「這一個打席會怎麼結束」，不預測整場勝負，也與上方的資料範圍無關" +
    "（使用固定的離線模型檔）。",
  intervalNote:
    "90% 區間是以收縮後有效樣本量做常態近似得到的模型敏感度範圍，不是統計信賴區間。",
  weightedNote:
    "把各結果機率乘上其後勝率所得的加權值，與現行場中勝率實質等效（差異在雜訊水準），" +
    "因此只用於拆解單一打席的影響，不用來預測比賽結果。",
  situationNote:
    "結果分布只取決於這組打者與投手；情境（局數、出局、壘上、比分）不改變結果機率，" +
    "只改變「若該結果發生，戰局會怎麼變」。",
  shrinkageNote:
    "估計以打者、投手各自的整體表現為主，兩人直接對戰樣本依其可靠度加權；" +
    "直接對戰佔比低時，這組數字更接近雙方各自的一般表現，不代表誰剋誰。",
} as const;

/**
 * 由查詢賽事類型與 API 回應判定面板狀態。
 * 判定只用 API 明示欄位與查詢參數，不引入任何自創統計閾值。
 *
 * @param kindCode 上方查詢的賽事類型（A／C／E）
 * @param response API 回應；null＝尚未取得（呼叫端以載入態處理）
 * @param failed   請求層失敗（非 200／網路／解析錯誤）
 */
export function derivePaSimState(
  kindCode: Kind,
  response: PaSimResponse | null,
  failed: boolean,
): PaSimState {
  // 母體不符先於一切：不對不受支援的賽事類型發出請求，也不顯示任何機率。
  if (kindCode !== SUPPORTED_KIND) return { kind: "unsupported", kindCode };
  if (failed) return { kind: "api_error" };
  // null 只在呼叫端已結束載入卻無回應時出現（防禦性 fail-closed，不推測數字）。
  if (response === null) return { kind: "unavailable", reason: "服務未回傳可用回應" };
  if (response.available === false) {
    const reason = response.reason ?? "";
    return reason.includes("artifact")
      ? { kind: "artifact_missing", reason }
      : { kind: "unavailable", reason };
  }

  // 契約防禦：API 若改動結果集合（新增／改名 outcome），寧可整段不顯示。
  const outcomes: Partial<Record<PaOutcomeKey, unknown>> = response.outcomes;
  const missing = ALL_OUTCOME_KEYS.filter((key) => outcomes[key] === undefined);
  if (missing.length) return { kind: "invariant_failed", sum: null, missing };
  const sum = outcomeProbabilitySum(response);
  if (Math.abs(sum - 1) > SUM_TOLERANCE) {
    return { kind: "invariant_failed", sum, missing: [] };
  }

  const { hitter_pa: hitterPa, pitcher_pa: pitcherPa } = response.sample;
  if (hitterPa <= 0 && pitcherPa <= 0) return { kind: "league_fallback", side: "both" };
  if (hitterPa <= 0) return { kind: "league_fallback", side: "hitter" };
  if (pitcherPa <= 0) return { kind: "league_fallback", side: "pitcher" };

  return { kind: "ok", data: response };
}

/** 七種結果機率總和（對帳用；缺鍵時以 0 計，交由 invariant 判定攔下）。 */
export function outcomeProbabilitySum(data: PaSimOk): number {
  return ALL_OUTCOME_KEYS.reduce(
    (total, key) => total + (data.outcomes[key]?.probability ?? 0),
    0,
  );
}

/**
 * 把 API 的主隊視角 delta_wp 翻成「打者方視角」：正＝對打者這一方有利。
 * half="2"（下半）打者屬主隊故同號，half="1"（上半）打者屬客隊故反號。
 * 只翻號向，不改變量值（統計由 API 決定）。
 */
export function batterSideDelta(half: PaState["half"], deltaWp: number): number {
  return half === "2" ? deltaWp : -deltaWp;
}

/** 打者方在此情境的隸屬（用於標示視角，避免主客混淆）。 */
export function batterSide(half: PaState["half"]): "home" | "away" {
  return half === "2" ? "home" : "away";
}

/**
 * 主隊勝率換算為打者方勝率。單場勝負為零和事件，故客隊視角＝1 − 主隊勝率；
 * 這是視角轉換而非重新估計，量值仍完全由 API 決定。
 */
export function batterSideWinProbability(half: PaState["half"], homeWp: number): number {
  return half === "2" ? homeWp : 1 - homeWp;
}

/** 壘上狀態顯示（API 的 bases 為 `_`／`1`／`2`／`3` 三格字串）。 */
export const BASES_OPTIONS: readonly { value: string; label: string }[] = [
  { value: "___", label: "壘上無人" },
  { value: "1__", label: "一壘有人" },
  { value: "_2_", label: "二壘有人" },
  { value: "__3", label: "三壘有人" },
  { value: "12_", label: "一二壘有人" },
  { value: "1_3", label: "一三壘有人" },
  { value: "_23", label: "二三壘有人" },
  { value: "123", label: "滿壘" },
];

export function basesLabel(bases: string): string {
  return BASES_OPTIONS.find((option) => option.value === bases)?.label ?? bases;
}

/** 中性預設情境：一局上半、無人出局、壘上無人、0–0（不預設高槓桿戲劇情境）。 */
export const DEFAULT_PA_STATE: PaState = {
  inning: 1,
  half: "1",
  bases: "___",
  outs: 0,
  away_score: 0,
  home_score: 0,
};

/** 情境摘要（供標題與圖表文字替代列表使用）。 */
export function stateSummary(state: PaState): string {
  const half = state.half === "1" ? "上" : "下";
  return (
    `${state.inning} 局${half}半・${state.outs} 出局・${basesLabel(state.bases)}・` +
    `客 ${state.away_score}－主 ${state.home_score}`
  );
}

/** 機率格式：百分比一位小數。 */
export function fmtProbability(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

/** 勝率變化格式：百分點一位小數、帶正負號（− 用 U+2212 對齊數字寬度）。 */
export function fmtDeltaPoints(value: number): string {
  const points = value * 100;
  const sign = points >= 0 ? "+" : "−";
  return `${sign}${Math.abs(points).toFixed(1)}`;
}
