// 球隊頁「球風」區塊的 view-model 與文案單點（UX-TEAM-STYLE1；沿 PREGAME_COPY 模式）。
// 消費端（style-section.tsx）不得自寫使用者可見字串——全部集中本檔，
// 讓 team-style.test.ts 得以對文案表逐字掃描設計約束：
//
// 1. 守備效率列**零形容詞**：desc/note 皆空字串，只呈現數字與排名（約束 3）。
// 2. 先發吃局／三振型投手必標「本季」；選球紀律可標「具跨季延續性」（約束 3）。
// 3. **零預測性語言**：任何字串不得連結賽果（勝率/戰績/預測…；約束 5）。
// 4. 教練名僅時間標記，文案不得暗示「某教練時期有一致風格」（約束 2）。
// 5. 不用隊伍非官方暱稱（文案紅線）。
//
// 語意判定在後端做一次（semantics discriminator）；本檔只做 semantics → 文案映射。

// —— API 契約（鏡射 GET /api/v1/teams/{code}/style；欄位名與後端一致故 snake_case）——

export type TeamStyleSemantics =
  | "cross_season_stable"
  | "current_season_only"
  | "numbers_only"
  | "usable";

export type TeamStyleAxisKey =
  | "speed" | "smallball" | "power" | "discipline"
  | "starter_ip" | "pitch_k" | "defense";

export type TeamStyleAxisMeta = {
  key: TeamStyleAxisKey;
  label: string;
  semantics: TeamStyleSemantics;
};

export type TeamStyleAxisValue = {
  z: number;
  /** 凍結軸原始值（rate）；discipline 為複合軸無單一 raw。 */
  raw: number | null;
  /** 同季全隊 raw 算術平均（z 計算裡的同一個均值；歷史圖聯盟參考線用）。 */
  league_raw_mean: number | null;
  /** 該季該軸聯盟名次（z 由高至低，1 = 最高）。 */
  rank: number;
  counts: Record<string, number>;
};

export type TeamStyleSeason = {
  year: number;
  team_code: string;
  team_name: string;
  n_teams: number;
  in_progress: boolean;
  /** 該季主教練（TEAM-STYLE2 判定；不可判定或覆蓋外年份為 null＝不標）。 */
  manager: string | null;
  axes: Record<TeamStyleAxisKey, TeamStyleAxisValue>;
};

export type TeamStyleResponse = {
  team: string;
  franchise: string;
  scope: "full_season";
  axes: TeamStyleAxisMeta[];
  seasons: TeamStyleSeason[];
};

// —— 數字格式化（純函式）——

export const formatZ = (z: number): string => (z >= 0 ? `+${z.toFixed(2)}` : z.toFixed(2));
export const clampZ = (z: number): number => Math.max(-2, Math.min(2, z));
const pct1 = (v: number): string => `${(v * 100).toFixed(1)}%`;
const f3 = (v: number): string => v.toFixed(3).replace(/^0\./, ".");
/** 出局數 → 棒球局數記法（540 出局 → "180"、542 → "180.2"）。 */
export const outsToIp = (outs: number): string => {
  const rem = outs % 3;
  return rem ? `${Math.floor(outs / 3)}.${rem}` : `${Math.floor(outs / 3)}`;
};

// —— 軸級文案表（單點；掃描對象）——

export type TeamStyleAxisCopy = {
  /** 一句話說明（沿凍結 spec §0.2 描述語意）；defense 依約束 3 為空。 */
  desc: string;
  /** 穩定性語意標注（約束 3 逐軸固定）；defense 依約束 3 為空。 */
  note: string;
  /** 明細（原始次數＋rate；只有數字，形容詞不進這裡）。 */
  detail: (v: TeamStyleAxisValue) => string;
  /** 歷史圖 raw 值的軸刻度／tooltip 格式（凍結 spec 的率值）；
   *  discipline 複合軸無單一 raw 故無此格式（歷史圖退回 z 呈現）。 */
  formatRaw?: (v: number) => string;
};

export const TEAM_STYLE_COPY: Record<TeamStyleAxisKey, TeamStyleAxisCopy> = {
  speed: {
    desc: "上壘後啟動盜壘的頻率",
    note: "跨季延續偏弱",
    detail: (v) => `盜壘企圖 ${(v.counts.sb ?? 0) + (v.counts.cs ?? 0)} 次`
      + (v.raw != null ? `（企圖率 ${pct1(v.raw)}）` : ""),
    formatRaw: pct1,
  },
  smallball: {
    desc: "犧牲短打換推進的使用頻率",
    note: "季內樣本偏噪",
    detail: (v) => `犧短 ${v.counts.sh ?? 0} 次`
      + (v.raw != null ? `（佔打席 ${pct1(v.raw)}）` : ""),
    formatRaw: pct1,
  },
  power: {
    desc: "進攻依賴長打額外壘打的程度",
    note: "季內樣本偏噪",
    detail: (v) => (v.raw != null ? `ISO ${f3(v.raw)}` : "ISO —")
      + `（額外壘打 ${v.counts.extra_bases ?? 0}）`,
    formatRaw: f3,
  },
  discipline: {
    desc: "多選保送、少吃三振",
    note: "",
    detail: (v) => `保送 ${v.counts.bb ?? 0} 次・三振 ${v.counts.so ?? 0} 次`,
  },
  starter_ip: {
    desc: "先發投手吃局的比重",
    note: "季內成立、跨季不延續",
    detail: (v) => `先發 ${outsToIp(v.counts.starter_outs ?? 0)} 局／全隊 ${outsToIp(v.counts.outs ?? 0)} 局`,
    formatRaw: pct1,
  },
  pitch_k: {
    desc: "投手群以三振解決打者的比例",
    note: "季內成立、跨季不延續",
    detail: (v) => `三振 ${v.counts.so_a ?? 0} 次`
      + (v.raw != null ? `（K% ${pct1(v.raw)}）` : ""),
    formatRaw: pct1,
  },
  // 守備效率：約束 3——只放數字與排名，零形容詞、零傾向描述。
  defense: {
    desc: "",
    note: "",
    detail: (v) => (v.raw != null ? `DER ${f3(v.raw)}` : "DER —"),
    formatRaw: f3,
  },
};

/** semantics → 徽章文案（判定在後端；此處只映射）。null＝不掛徽章。 */
export const SEMANTICS_BADGE: Record<TeamStyleSemantics, string | null> = {
  cross_season_stable: "具跨季延續性",
  current_season_only: "本季",
  numbers_only: null,
  usable: null,
};

// —— 區塊層級文案（同樣入掃描範圍）——

export const TEAM_STYLE_SECTION = {
  title: "球風",
  scopeBadge: "全年",                 // 約束 7：全季口徑，區塊內明示
  inProgressBadge: "賽季進行中",      // 約束 8
  subtitle: "七個描述性風格軸：描述這支球隊打球的樣子，與同季聯盟相比（季內 z 值）。",
  radarCaption: "0 = 當季聯盟平均；顯示截 ±2。",
  detailHeading: "軸明細",
  detailCaption: "原始數值與聯盟排名（同季內比較）。",
  historyHeading: "歷史逐季",
  historyCaption: "逐季原始值；虛線＝當季聯盟平均（聯盟環境逐年變化的參照）。z 與排名見資料點 tooltip。",
  historyCaptionZ: "選球紀律為複合軸（無單一原始值），以逐季季內 z 呈現；排名見資料點 tooltip。",
  legendTeam: "球隊",
  legendLeague: "聯盟平均",
  tooltipLeagueLabel: "聯盟平均",
  yearSelectorLabel: "選擇球季",
  axisSelectorLabel: "選擇風格軸",
  managerFootnote: "總教練名僅作時間標記（起迄＝可判定的任期季；現任開區間）；不可判定年份不標示。",
  emptyState: "該年度尚無球風資料（逐場資料自 2018 年起）。",
  rankLabel: (rank: number, n: number) => `聯盟第 ${rank}（/${n} 隊）`,
  managerMarkerLabel: (name: string, from: number, to: number) =>
    from === to ? `${name} ${from}` : `${name} ${from}–${to}`,
  /** 現任（任期止於進行中賽季）＝開區間「名 起–」。 */
  managerMarkerLabelOpen: (name: string, from: number) => `${name} ${from}–`,
  inProgressNote: (years: number[]) => `${years.join("、")} 賽季進行中（空心點）。`,
} as const;

// —— 教練時間標記（約束 2：逐季分段；教練名只標時間）——

export type ManagerRun = { name: string; from: number; to: number };

/**
 * 從逐季 manager 序列導出任期段（閉區間）：與**最近一個已知**主教練不同名即開新段；
 * 同名延伸段的迄年。迄年＝該教練**最後一個被判定為主教練的季**——資料邊界外
 * （2026 各隊、統一 2019 等不可判定季）不延伸、不用 managers.to_year 補
 * （to_year＝維基最後戰績列年份非卸任年，語意陷阱）。
 * 不可判定季（null）跳過、不斷開——同名跨過未知季視為同一段（未知季無從宣稱換帥）。
 */
export function managerRuns(
  seasons: Pick<TeamStyleSeason, "year" | "manager">[],
): ManagerRun[] {
  const runs: ManagerRun[] = [];
  for (const s of [...seasons].sort((a, b) => a.year - b.year)) {
    if (s.manager == null) continue;
    const last = runs[runs.length - 1];
    if (last && last.name === s.manager) last.to = s.year;
    else runs.push({ name: s.manager, from: s.year, to: s.year });
  }
  return runs;
}

/**
 * 任期身分色輪替色盤：自 `--chart-2` 起，**扣掉 chart-1（資料折線專用）與
 * chart-6（中性灰槽）**——中性灰在圖表語彙裡保留給參考元素（聯盟均線／基準線
 * 正是降飽和灰），任期身分色不得與參考元素同色系（需求方裁定）。超出循環。
 */
export function tenurePaletteFrom(series: string[]): string[] {
  return series.filter((_, i) => i !== 0 && i !== 5);
}

// —— 歷史逐季 view-model（display 層只認此契約；聯盟基準不得靜默消失）——

export type TeamStyleHistoryPoint = {
  year: number;
  value: number | null;
  league: number | null;
  in_progress: boolean;
  n_teams: number;
  v: TeamStyleAxisValue;
};

export type TeamStyleHistoryVM = {
  mode: "raw" | "z";
  points: TeamStyleHistoryPoint[];
  /** raw 模式：聯盟平均「序列」必須渲染（降飽和點虛線）。 */
  leagueSeries: boolean;
  /** z 模式：y=0 基準線必須渲染並標示（z=0 即聯盟平均，語意一致）。 */
  zeroBaseline: boolean;
  /** 基準／均線的標示文案（兩模式共用「聯盟平均」）。 */
  baselineLabel: string;
};

/**
 * 歷史逐季圖的 view-model：每一軸**恰有一種**聯盟基準呈現——
 * raw 模式畫聯盟平均序列、z 退回模式畫標示「聯盟平均」的 y=0 基準線。
 * 元件必須依此渲染（team-style.test.ts 釘住，防止均線再次靜默消失）。
 */
export function buildHistoryVM(
  axisKey: TeamStyleAxisKey,
  seasons: TeamStyleSeason[],
): TeamStyleHistoryVM {
  const rawMode = TEAM_STYLE_COPY[axisKey].formatRaw != null;
  return {
    mode: rawMode ? "raw" : "z",
    points: seasons.map((s) => {
      const v = s.axes[axisKey];
      return {
        year: s.year,
        value: rawMode ? v.raw : v.z,
        league: rawMode ? v.league_raw_mean : null,
        in_progress: s.in_progress,
        n_teams: s.n_teams,
        v,
      };
    }),
    leagueSeries: rawMode,
    zeroBaseline: !rawMode,
    baselineLabel: TEAM_STYLE_SECTION.legendLeague,
  };
}
