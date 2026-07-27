// PregameCard view-model（UX-OUTCOME-HOME；PRODUCT_UX_BLUEPRINT v0.2 §5.1）。
// 本模組是「可嵌入賽前勝率卡」的單一契約：消費端（UX-GAME-HOME1 等）自行抓
// GET /api/v1/outcome/pregame 後，把 response＋單場 gameRef 丟進 resolvePregameCard()
// 取得 discriminated union，再交給 <PregameCard/> 渲染。元件本身不抓資料、
// 不決定區塊排序、不修改首頁文案。
//
// 文案紅線（驗收條件，勿散寫字串）：
// 1. 卡片只顯示點機率＋1 個主要訊號；區間一律不進卡片，也不出現「信賴區間」字樣
//    （賽事頁／方法頁固定稱「模型敏感度區間」，不屬本卡）。
// 2. 缺模型／不支援／未就緒時不補 50% 假數字，只給不可用說明，且不阻塞外層賽程卡。

import { methodologyHref } from "./methodology-anchors.ts";

// —— API 契約（鏡射 GET /api/v1/outcome/pregame；欄位名與後端一致故用 snake_case）——

export type PregameSignalDirection = "higher_favors_home" | "lower_favors_home";

export type PregameItemSignal = {
  key: string;
  raw: number | null;
  direction: PregameSignalDirection;
};

export type PregameItem = {
  season: number;
  game_sno: number;
  game_date: string;
  home: string;
  away: string;
  home_win_probability: number;
  /** API 有回，但卡片契約禁止渲染（區間退賽事頁／方法頁）。 */
  model_interval_90?: [number, number] | null;
  /** group（strength/offense/suppression/schedule）→ 該群被模型選中的訊號。 */
  signals: Record<string, PregameItemSignal>;
};

export type PregameResponse = {
  available: boolean;
  reason?: string;
  trained_through?: number;
  signals?: Record<string, string>;
  items?: PregameItem[];
  /** 產生 items 這些機率的模型是不是最新回測那一版。與 items 同在這一份 response 內，
   *  卡片因此天生滿足「機率與其 serving 狀態同源」——不得改成另外抓一次。 */
  serving?: PregameServingMeta;
};

// —— serving 降級狀態（ML-OUTCOME-SIMPLE-LEAK2 紅線 5）——
// 放在本模組而非 daily-summary，是因為三個渲染賽前勝率的介面（首頁、方法頁、賽況頁）
// 都要用同一套說法，而 daily-summary 依賴本模組——反向 import 會成環。

/** 賽前模型的 serving 狀態（ML-OUTCOME-SIMPLE-LEAK2 紅線 5）。
 *
 * serving_previous＝無法證明「serving 就是最新回測的產出」，點機率仍可能來自**上一版**
 * 模型。這時機率照樣算得出來，所以卡片不會退成不可用——但介面必須明講現正沿用哪一版、
 * 以及是哪一種成因（`degradation`），不能無聲照顯。unavailable 才是整段沒有模型。
 *
 * `backtest_unknown`＝連最新回測的閘門結果都讀不到（DB 例外／無紀錄／gate 欄缺席）。
 * 它與 `version_mismatch` 分開，是因為後者才有「該次回測通過了閘門」這個正面事實；
 * 把未知併進去就會變成憑空宣稱閘門已通過（iteration 5 查核 F1）。
 */
export type PregameDegradation =
  | "gate_failed"
  | "version_unknown"
  | "backtest_unknown"
  | "version_mismatch";

export type PregameServingMeta = {
  status: "serving_current" | "serving_previous" | "unavailable";
  serving_version?: string | null;
  backtest_version?: string | null;
  backtest_deployable?: boolean | null;
  degradation?: PregameDegradation | null;
};

/** 降級告示；serving 正常或整段不可用時回 null（後者由卡片各自的不可用文案負責）。
 *
 * 成因由後端的 `degradation` 判別碼決定，前端只做映射。**能講出「閘門」結果的只有兩處**，
 * 而且各自都要有這份 response 裡的正面證據：
 *
 * - `gate_failed` 才可以說「未通過部署閘門」——另外幾種是版本紀錄對不上或根本讀不到
 *   回測，與閘門結果無關，講成閘門失敗就是說錯話（deploy→refresh 窗口即 version_unknown，
 *   那次回測其實是 7/7 通過的）。
 * - `version_mismatch` 的「該次回測本身已通過閘門」只在 `backtest_deployable === true`
 *   時才附註。後端已保證這條分支必為 true，但**前端不靠那個保證說出 PASS 這種話**：
 *   iteration 5 的缺陷就是後端把「未知」壓成同一個判別碼，前端照著保證講，於是憑空
 *   宣稱閘門已通過。判別碼可能出錯，`backtest_deployable` 是這句話唯一的直接證據。
 *
 * default 分支刻意只給不含任何閘門宣稱的中性說法：後端未來新增判別碼時，最壞情況是
 * 講得比較籠統，而不是被誤述成別的成因（`version_unknown` 因此保留自己的 case）。
 */
export function pregameServingNotice(axis: PregameServingMeta): string | null {
  if (axis.status !== "serving_previous") return null;
  const backtest = axis.backtest_version ? `最新回測 ${axis.backtest_version}` : "最新回測紀錄";
  const serving = axis.serving_version ?? "（未記錄）";
  switch (axis.degradation) {
    case "gate_failed":
      return `${backtest}未通過部署閘門，現正沿用版本 ${serving}；以下機率並非最新回測所對應的模型輸出。`;
    case "version_mismatch": {
      const gateNote = axis.backtest_deployable === true ? "（該次回測本身已通過閘門）" : "";
      return `serving 版本 ${serving} 與${backtest}不一致${gateNote}；以下機率並非最新回測所對應的模型輸出。`;
    }
    case "version_unknown":
      return `serving 模型未記錄版本，無法確認是否為${backtest}的產出；以下機率可能來自舊版模型。`;
    case "backtest_unknown":
      return `無法確認${backtest}的部署判定結果，因此也無從確認 serving 版本 ${serving} 是否為它的產出；以下機率可能來自舊版模型。`;
    default:
      return "無法確認 serving 是否為最新回測的產出；以下機率可能來自舊版模型。";
  }
}

/** 消費端指定要渲染哪一場；kind_code 用來判定模型支援範圍（僅一軍例行賽 A）。 */
export type PregameGameRef = { season: number; game_sno: number; kind_code: string };

// —— 文案（紅線集中單點；測試對本表整體掃描）——

export const PREGAME_COPY = {
  eyebrow: "賽前勝率",
  probabilityLabel: "主隊勝率",
  methodologyLabel: "模型方法",
  signalUnavailable: "今日訊號資料不足",
  trainedThroughPrefix: "模型資料至",
  trainedThroughSuffix: "季",
  missingArtifact: "模型尚未建置，暫無賽前預測",
  unsupported: "此賽事類型不在賽前模型範圍",
  pending: "預測準備中，資料到齊後提供",
  error: "預測服務暫時無法使用",
  favorsHome: "利主隊",
  favorsAway: "利客隊",
  favorsEven: "兩隊持平",
} as const;

// —— 主要訊號 ——
// 卡片只給 1 個主訊號。API 每群各回一個訊號，無逐場標準化係數可比大小，
// 故採固定群優先序（透明、可覆核，不做無依據的逐場排序）：
//   suppression（失分抑制，含唯一與「本場」直接綁定的先發投手訊號）
//   → strength（整體戰力背景）→ offense（打線）→ schedule（賽程）。
// 取第一個 raw 非缺值的群；先發未公布等缺值時自然退位到下一群。
export const PRIMARY_SIGNAL_GROUP_ORDER = [
  "suppression",
  "strength",
  "offense",
  "schedule",
] as const;

/** 訊號 key → 卡片顯示標籤（與後端 features/outcome.py 中文語意對齊，加「差」明示主−客）。 */
export const SIGNAL_LABELS: Record<string, string> = {
  winrate_diff: "季內勝率差",
  prior_winpct_diff: "上季戰力差",
  runs_scored_diff: "場均得分差",
  runs_allowed_diff: "場均失分差",
  starter_era_diff: "先發投手ERA差",
  prior_team_ops_diff: "上季團隊OPS差",
  team_ops_now_diff: "當季團隊OPS差",
  rest_days_diff: "休息天數差",
};

/** 訊號 key → 數值格式（小數位與後綴）。 */
const SIGNAL_FORMAT: Record<string, { decimals: number; suffix?: string }> = {
  winrate_diff: { decimals: 3 },
  prior_winpct_diff: { decimals: 3 },
  runs_scored_diff: { decimals: 2, suffix: " 分" },
  runs_allowed_diff: { decimals: 2, suffix: " 分" },
  starter_era_diff: { decimals: 2 },
  prior_team_ops_diff: { decimals: 3 },
  team_ops_now_diff: { decimals: 3 },
  rest_days_diff: { decimals: 0, suffix: " 天" },
};

export type PregamePrimarySignal = {
  key: string;
  label: string;
  valueText: string;
  favors: "home" | "away" | "even";
  favorsText: string;
};

// —— view model（discriminated union）——

export type PregameCardModel =
  | {
      status: "available";
      /** 點機率（0–1），僅此一個機率；不含任何區間欄位。 */
      homeWinProbability: number;
      /** 顯示文字（整數 %；>99.5% 顯示 ">99%"、<0.5% 顯示 "<1%"，不給假精度）。 */
      probabilityText: string;
      primarySignal: PregamePrimarySignal | null;
      trainedThroughText: string | null;
      /** 降級告示：這個機率不是最新回測那一版模型算的。由**同一份 response** 推導，
       *  正常時為 null。首頁把它擺在賽事列表上方（一次），故該路徑刻意留 null。 */
      servingNotice: string | null;
      methodologyHref: string;
    }
  | {
      status: "missing_artifact" | "unsupported" | "pending" | "error";
      message: string;
      methodologyHref: string;
    };

export type ResolvePregameInput = {
  /** API response；fetch 失敗時傳 null 並設 fetchFailed。 */
  response: PregameResponse | null;
  game: PregameGameRef;
  fetchFailed?: boolean;
};

const HREF = methodologyHref("pregame");

function unavailable(
  status: "missing_artifact" | "unsupported" | "pending" | "error",
  message: string
): PregameCardModel {
  return { status, message, methodologyHref: HREF };
}

export function formatProbability(p: number): string {
  const pct = p * 100;
  if (pct > 99.5) return ">99%";
  if (pct < 0.5) return "<1%";
  return `${Math.round(pct)}%`;
}

function formatSignalValue(key: string, raw: number): string {
  const fmt = SIGNAL_FORMAT[key] ?? { decimals: 2 };
  const sign = raw > 0 ? "+" : "";
  return `${sign}${raw.toFixed(fmt.decimals)}${fmt.suffix ?? ""}`;
}

export function pickPrimarySignal(
  signals: Record<string, PregameItemSignal>
): PregamePrimarySignal | null {
  for (const group of PRIMARY_SIGNAL_GROUP_ORDER) {
    const signal = signals[group];
    if (!signal || signal.raw == null || !Number.isFinite(signal.raw)) continue;
    const towardHome =
      signal.direction === "lower_favors_home" ? -signal.raw : signal.raw;
    const favors = towardHome > 0 ? "home" : towardHome < 0 ? "away" : "even";
    return {
      key: signal.key,
      label: SIGNAL_LABELS[signal.key] ?? signal.key,
      valueText: formatSignalValue(signal.key, signal.raw),
      favors,
      favorsText:
        favors === "home"
          ? PREGAME_COPY.favorsHome
          : favors === "away"
            ? PREGAME_COPY.favorsAway
            : PREGAME_COPY.favorsEven,
    };
  }
  return null;
}

/** 把 pregame API response＋單場 gameRef 解成卡片 view model；永不 throw、永不造 50%。 */
export function resolvePregameCard(input: ResolvePregameInput): PregameCardModel {
  const { response, game, fetchFailed } = input;
  if (fetchFailed || response == null) return unavailable("error", PREGAME_COPY.error);
  // 模型只涵蓋一軍例行賽（game_features 全史 kind A）；其他賽別誠實標示不支援。
  if (game.kind_code !== "A")
    return unavailable("unsupported", PREGAME_COPY.unsupported);
  if (!response.available)
    return unavailable("missing_artifact", PREGAME_COPY.missingArtifact);
  const item = (response.items ?? []).find(
    (it) => it.season === game.season && it.game_sno === game.game_sno
  );
  if (!item || !Number.isFinite(item.home_win_probability))
    return unavailable("pending", PREGAME_COPY.pending);
  return {
    status: "available",
    homeWinProbability: item.home_win_probability,
    probabilityText: formatProbability(item.home_win_probability),
    primarySignal: pickPrimarySignal(item.signals ?? {}),
    trainedThroughText:
      response.trained_through != null
        ? `${PREGAME_COPY.trainedThroughPrefix} ${response.trained_through} ${PREGAME_COPY.trainedThroughSuffix}`
        : null,
    // 機率與 serving 狀態出自同一份 response——這就是不變式，不得改成另外抓一次。
    servingNotice: response.serving ? pregameServingNotice(response.serving) : null,
    methodologyHref: HREF,
  };
}
