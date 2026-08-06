// UX-GAME-RECAP1：單場打席事實流 [plate appearance fact stream] 的型別與純函式。
//
// 對應後端 `src/cpbl/models/pa_facts.py`（唯一事實來源）。前端**不重算 ΔRE24、不重刻
// 打席切界**——賽況頁 live 逐打席、賽後 recap、#79 探索器三個消費者共用同一份事實。
//
// 關鍵打席＝**|ΔWP|（勝率擺動）選取並直接顯示擺動量**（2026-08-06 需求方兩次裁決；
// brief 非目標欄已修訂留痕）。原「禁 WPA 排序」禁令精確化為：WP 機率**水平值**不作
// 宣稱（VAL1 中段 ±4–6pt 校準偏差），而序數選取與變化量顯示不依賴水平校準。
// 守門：`plate_appearances`（逐打席頁籤）**不帶 WP 欄位**——差異由後端資料守住；
// 擺動量只出現在 `key_plays`，且顯示處必附偏差揭露（見 /methodology#key-plays）。

export type FactPerson = { player_id: string; name: string | null };

export type PaFact = {
  pa_id: string | null;
  pa_index: number;
  state: "ready" | "non_pa" | "truncated" | "unreliable" | "reconciliation_required";
  inning: number | null;
  half: string | null;
  outs_before: number | null;
  bases_before: string[];
  away_score_before: number | null;
  home_score_before: number | null;
  /** 該打席**結束後**的比分（取終結事件的事件後快照，非加總推算）。 */
  away_score_after: number | null;
  home_score_after: number | null;
  hitter: FactPerson | null;
  end_hitter: FactPerson | null;
  pitcher: FactPerson | null;
  result_action: string | null;
  outcome_family: string | null;
  start_event_no: string | null;
  end_event_no: string | null;
  member_event_nos: string[];
  runs_on_play: number | null;
  delta_re24: number | null;
  /**
   * 該打席的**主隊勝率變化**（0–1；正＝主隊勝率上升），與賽況頁 WP 曲線同解算器、
   * 同視角、正負與曲線升降對齊。**只有 `key_plays` 的元素帶此欄**；逐打席頁籤的
   * `plate_appearances` 恆為 undefined。
   */
  delta_wp?: number | null;
  /** 打席前／後的主隊勝率水平值（0–1），供勝率條視覺化；同樣只出現在 `key_plays`。 */
  wp_before?: number | null;
  wp_after?: number | null;
  /** `wp_after` 是終場結果而非局面推算值 → 顯示夾層豁免（見 `win-prob-display.ts`）。 */
  wp_after_terminal?: boolean;
  unavailable_reason: string | null;
  /** 分差 ≥7 的事實旗標。|ΔWP| 選取下實測不會入選（81 場 0 命中），呈現層不再降飽和。 */
  garbage_time: boolean;
};

/** 關鍵打席選取準則的揭露（後端 `pa_facts.key_play_selection`）；缺關鍵打席時為 null。 */
export type KeyPlaySelection = {
  signal: "delta_wp" | "delta_re24";
  min_abs: number;
  degraded: boolean;
  reason: string | null;
};

export type FactDecisions = {
  winning_pitcher: FactPerson | null;
  losing_pitcher: FactPerson | null;
  closer: FactPerson | null;
  mvp: FactPerson | null;
  /** `official_pending`＝官方尚未給出勝敗投（當晚 snapshot 實測 2/5 才有）。 */
  availability: "available" | "official_pending";
};

/** 設計稿 §7 降級階梯；呼叫端必須據此揭露，不得把暫定當權威照顯。 */
export type RenderState =
  | "authoritative" | "provisional" | "provisional_simple"
  | "live" | "stale_live" | "pending" | "postponed" | "reconciling";

export type GameFacts = {
  season: number;
  kind_code: string;
  game_sno: number;
  source: "authoritative" | "provisional" | null;
  render_state: RenderState;
  reason: string | null;
  completed: boolean;
  final: { home_score: number; away_score: number; result?: string } | null;
  teams: { home: { code: string | null; name: string | null };
           away: { code: string | null; name: string | null } } | null;
  game_date?: string | null;
  venue?: string | null;
  decisions?: FactDecisions;
  conclusion: { shape: string; sentence: string; slots: Record<string, unknown>;
                focus_pa_index?: number } | null;
  plate_appearances: PaFact[];
  key_plays: PaFact[];
  key_play_selection: KeyPlaySelection | null;
  half_innings: Record<string, PaFact[]>;
  re_matrix: { span: string; kind_code: string };
};

/** recap 五塊可完整呈現的狀態（其餘走簡版或不進賽後態）。 */
export const isRecapReady = (facts: GameFacts | null): boolean =>
  !!facts && (facts.render_state === "authoritative" || facts.render_state === "provisional");

/** 是否需要在頁面級掛「暫定」揭露。 */
export const isProvisional = (facts: GameFacts | null): boolean =>
  !!facts && facts.source === "provisional";

export const halfKey = (inning: number | string, half: number | string) => `${inning}|${half}`;

export const halfLabel = (half: string | null): string =>
  String(half) === "1" ? "上" : String(half) === "2" ? "下" : "";

/** 局面脈絡文字（局數／出局／壘況）——圖示之外的文字替代，a11y 必需。 */
export function situationText(fact: Pick<PaFact, "inning" | "half" | "outs_before" | "bases_before">): string {
  const bases = fact.bases_before ?? [];
  const runners = bases.length === 0 ? "壘上無人"
    : bases.length === 3 ? "滿壘"
    : `${bases.map((b) => `${b === "1" ? "一" : b === "2" ? "二" : "三"}壘`).join("、")}有人`;
  return `${fact.inning ?? "—"} 局${halfLabel(fact.half)}　${fact.outs_before ?? "—"} 出局　${runners}`;
}

/** 打席前的分差文字（主隊視角絕對值），供關鍵打席的局面脈絡使用。 */
export function marginText(fact: Pick<PaFact, "away_score_before" | "home_score_before">): string {
  const { away_score_before: away, home_score_before: home } = fact;
  if (away === null || home === null) return "";
  if (away === home) return "平手";
  return `${Math.max(away, home)}–${Math.min(away, home)}`;
}

/**
 * 該打席得分**之後**的比分（客, 主）。
 *
 * 直接取事實流給的「終結事件事件後快照」，**不做加法**——livelog 的比分欄是事件後值，
 * 單一事件就結束的得分打席（首球全壘打）其起始列即終結列，用「打席前比分 + 進帳分數」
 * 推算會多加一次。缺任一欄回 null，**不猜**：比分寧可不顯示也不能顯示錯的。
 */
export function scoreAfterPlay(play: {
  away_score_after: number | null; home_score_after: number | null;
}): { away: number; home: number } | null {
  const { away_score_after: away, home_score_after: home } = play;
  if (away === null || home === null) return null;
  return { away, home };
}

export const signedDelta = (value: number | null): string =>
  value === null ? "—" : `${value > 0 ? "+" : value < 0 ? "−" : ""}${Math.abs(value).toFixed(2)}`;

/**
 * 勝率擺動的顯示標示：**受益隊＋恆正值**（如 `樂天桃猿 +19pt`）。
 *
 * 需求方 2026-08-06 樣式回饋：「上線版資訊比較少但可視度比較清楚，像『ＸＸＸ隊＋Ｏ％』
 * 就很明顯。」——與生產「關鍵時刻」卡同一套標示法。**內部資料維持主隊視角**
 * （`delta_wp` 正＝主隊上升），受益方轉換只發生在顯示層：讀者不必先知道誰是主隊、
 * 也不必解讀負號，就能讀出「這一打席把勝率推向誰、推了多少」。
 *
 * 取整數百分點是刻意的誠實：WP 水平值有已知 ±4–6 個百分點的校準偏差
 * （/methodology#winprob-validation），寫到小數點後一位是假精度。
 *
 * 回傳 null＝無擺動值或剛好持平（**不編一個受益隊**）。
 */
export function wpSwingLabel(
  value: number | null | undefined, homeName?: string | null, awayName?: string | null,
): { team: string; home: boolean; pt: number; text: string } | null {
  if (value === null || value === undefined || !Number.isFinite(value)) return null;
  const pt = Math.abs(Math.round(value * 100));
  if (value === 0) return null;
  const home = value > 0;
  const team = (home ? homeName : awayName) || (home ? "主隊" : "客隊");
  return { team, home, pt, text: `${team} +${pt}pt` };
}

/** 顯示用姓名：逐場來源優先，缺名才退回 ID（`cpbl.players` 會缺當季新登錄球員）。 */
export const personName = (person: FactPerson | null | undefined): string =>
  person ? (person.name ?? person.player_id) : "";

// ---------------------------------------------------------------------------
// 逐打席清單分組（live 逐打席與 linescore 展開共用）
// ---------------------------------------------------------------------------
export type PaGroup =
  | { kind: "pa"; hitter: string; name: string; pitcher: string; idxs: number[]; fact?: PaFact }
  | { kind: "sub"; gi: number };

type MinimalEvent = {
  main_event_no?: unknown; hitter_acnt?: unknown; hitter_name?: unknown;
  pitcher_name?: unknown; is_change_player?: unknown;
};

/**
 * 半局事件索引 → 逐打席分組。
 *
 * `facts` 缺席時**逐位元等同**於既有的「連續同打者」近似切法（換底不換臉的保證，
 * 由 `pa-groups.test.ts` 釘住）；提供 `facts` 時改用 canonical PA 的成員事件分組——
 * 打席中途代打不再被切成兩段、記錄歸屬依規則 9.15(b)。
 */
export function buildPaGroups(
  log: MinimalEvent[], events: number[], facts?: PaFact[] | null,
): PaGroup[] {
  const groups: PaGroup[] = [];
  const byEventNo = new Map<string, PaFact>();
  for (const fact of facts ?? []) {
    for (const eventNo of fact.member_event_nos ?? []) byEventNo.set(String(eventNo), fact);
  }
  type PaEntry = Extract<PaGroup, { kind: "pa" }>;
  // canonical 路徑要**跨換人列**續同一個打席（打席中途代打就是靠換人列公告的），
  // 故不能只看 `groups[groups.length - 1]`——那在換人列之後永遠是 sub。
  let openFact: PaFact | null = null;
  let openGroup: PaEntry | null = null;

  const legacyPush = (gi: number, ev: MinimalEvent) => {
    const last = groups[groups.length - 1];
    if (last && last.kind === "pa" && !last.fact && last.hitter === String(ev.hitter_acnt)) {
      last.idxs.push(gi);
      return;
    }
    const entry: PaEntry = {
      kind: "pa", hitter: String(ev.hitter_acnt), name: String(ev.hitter_name ?? ""),
      pitcher: String(ev.pitcher_name ?? ""), idxs: [gi],
    };
    groups.push(entry);
  };

  for (const gi of events) {
    const ev = log[gi];
    if (ev.is_change_player || !ev.hitter_acnt) { groups.push({ kind: "sub", gi }); continue; }
    if (byEventNo.size === 0) { legacyPush(gi, ev); continue; }

    const fact = byEventNo.get(String(ev.main_event_no));
    // canonical 對不到（來源修正／暫態）→ 該列退回近似切法，不整段消失
    if (!fact) {
      openFact = null;
      openGroup = null;
      legacyPush(gi, ev);
      continue;
    }
    if (openFact === fact && openGroup) { openGroup.idxs.push(gi); continue; }
    const entry: PaEntry = {
      kind: "pa",
      hitter: String(fact.hitter?.player_id ?? ev.hitter_acnt),
      // 記錄歸屬打者（規則 9.15(b)）優先；缺名退回該列的官方姓名
      name: personName(fact.hitter) || String(ev.hitter_name ?? ""),
      pitcher: personName(fact.pitcher) || String(ev.pitcher_name ?? ""),
      idxs: [gi], fact,
    };
    groups.push(entry);
    openFact = fact;
    openGroup = entry;
  }
  return groups;
}
