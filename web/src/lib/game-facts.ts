// UX-GAME-RECAP1：單場打席事實流 [plate appearance fact stream] 的型別與純函式。
//
// 對應後端 `src/cpbl/models/pa_facts.py`（唯一事實來源）。前端**不重算 ΔRE24、不重刻
// 打席切界**——賽況頁 live 逐打席、賽後 recap、#79 探索器三個消費者共用同一份事實。
//
// 紅線：|ΔRE24| 是關鍵打席的唯一排序依據；**禁 WPA／WP 參與排序**（WP 全 scope 時間外
// 驗證 unsupported，只作參考資訊，見 /methodology#winprob）。

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
  unavailable_reason: string | null;
  /** 分差 ≥7：呈現層降飽和，**不剔除、不加權**（v1.3 排序契約）。 */
  garbage_time: boolean;
};

export type ScoringHalf = {
  inning: number;
  half: string;
  runs: number;
  plays: {
    pa_index: number; pa_id: string | null; hitter: FactPerson | null;
    result_action: string | null; runs: number; delta_re24: number | null;
    start_event_no: string | null; end_event_no: string | null;
  }[];
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
  scoring_chain: ScoringHalf[];
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

export const signedDelta = (value: number | null): string =>
  value === null ? "—" : `${value > 0 ? "+" : value < 0 ? "−" : ""}${Math.abs(value).toFixed(2)}`;

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
