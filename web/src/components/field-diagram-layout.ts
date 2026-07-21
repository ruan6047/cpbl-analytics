// 守備位置圖的純佈局邏輯（UI-FIELD-DIAGRAM1）。與 React 分離，才能以 node --test 測。
//
// 這張圖是「守位身分圖」，不宣稱公尺級空間精確度（見研究 §1），但仍須保留棒球站位語意。
// 轉播共通骨架：外野沿扇形展開、游擊／二壘在二壘兩側、一三壘手靠邊線、投捕位於中軸。
// 格位採經驗證的不相交座標，兼顧轉播式空間關係與小尺寸可讀性。

/** 守位鍵。與 `cpbl.game_livelog.defend_station_code` 的一軍實測值對齊，供賽況頁沿用。 */
export type FieldPosition = "LF" | "CF" | "RF" | "3B" | "SS" | "2B" | "1B" | "P" | "C";

/** 每格的顯示內容，由呼叫端決定；本元件不假設資料來源。 */
export type FieldCellContent = {
  /** 主標；省略時用守位中文名。 */
  main?: string;
  /** 副標（局數／場數／球員名等自由字串）；null 或省略即不顯示。 */
  sub?: string | null;
  /** 右側短標（例：棒次 1–9）；不適合放長文字。 */
  meta?: string | null;
  /** 提供時整格可點（例：連向球員頁）；省略即不可點。 */
  href?: string | null;
};

export type FieldCells = Partial<Record<FieldPosition, FieldCellContent>>;

export const POSITION_LABEL: Record<FieldPosition, string> = {
  LF: "左外野", CF: "中外野", RF: "右外野",
  "3B": "三壘", SS: "游擊", "2B": "二壘", "1B": "一壘",
  P: "投手", C: "捕手",
};

/** 由上而下、由左而右的閱讀順序（也是 aria-label 的敘述順序）。 */
export const FIELD_POSITIONS: FieldPosition[] = ["LF", "CF", "RF", "3B", "SS", "2B", "1B", "P", "C"];

// ---- 幾何 ----
// 格位以固定網格排列，任兩格的矩形不相交；文字置中並截斷於格內，故文字框亦不可能相交。
// 縱向間距 18 > 任何字級的 bbox 溢出量，橫向間距 ≥ 8 再加左右各 6 的內距。

export const VIEW_W = 360;
export const VIEW_H = 300;
export const CELL_H = 38;
/** 左側守位碼徽章寬度。 */
export const BADGE_W = 24;
/** 右側短標寬度；僅有 meta 時保留。 */
export const META_W = 15;
/** 文字左右內距（單邊）。 */
export const PAD_X = 4;
export const MAIN_FONT = 11;
export const SUB_FONT = 9;
/** 主標／副標基線相對格頂的位移。有副標時主標上移，讓兩行在格內視覺置中。 */
export const MAIN_BASELINE = 16;
export const MAIN_BASELINE_ALONE = 23;
export const SUB_BASELINE = 30;

type Slot = { x: number; y: number; w: number };

const SLOTS: Record<FieldPosition, Slot> = {
  // 看台／捕手視角：左外在左、右外在右。
  LF: { x: 12, y: 54, w: 100 },
  CF: { x: 130, y: 22, w: 100 },
  RF: { x: 248, y: 54, w: 100 },
  // 中線手比角落內野手更深，還原實際防區層次。
  "3B": { x: 8, y: 174, w: 88 },
  SS: { x: 75, y: 126, w: 88 },
  "2B": { x: 197, y: 126, w: 88 },
  "1B": { x: 264, y: 174, w: 88 },
  P: { x: 130, y: 180, w: 100 },
  C: { x: 130, y: 248, w: 100 },
};

export type LaidOutCell = {
  code: FieldPosition | "DH";
  x: number; y: number; w: number; h: number;
  /** 格中心 x，文字以此為 text-anchor="middle" 的錨點。 */
  cx: number;
  /** 守位碼徽章右側內容區中心。 */
  contentCx: number;
  main: string;
  sub: string | null;
  meta: string | null;
  /** 整格連結（有則可點）。 */
  href: string | null;
  /** 是否有資料。無資料者低調呈現，讓讀者看得出哪些守位沒有資料。 */
  used: boolean;
};

/**
 * 全形字寬約 1em、半形約 0.6em 的保守估計。SVG 在 server render 時量不到真實字寬，
 * 只能估；估寬後截斷，再由瀏覽器端 getBBox 相交檢測驗收（見卡片驗證段）。
 */
export function textWidth(text: string, fontSize: number): number {
  let em = 0;
  for (const ch of text) {
    // 半形：ASCII 與半形標點；其餘（CJK、全形標點）以全形計
    em += /[ -~｡-ﾟ]/.test(ch) ? 0.6 : 1;
  }
  return em * fontSize;
}

/** 截斷到不超過 maxWidth；截斷時以 `…` 結尾。maxWidth 容不下任何字元時回空字串。 */
export function fitText(text: string, maxWidth: number, fontSize: number): string {
  if (textWidth(text, fontSize) <= maxWidth) return text;
  const ellipsis = "…";
  const budget = maxWidth - textWidth(ellipsis, fontSize);
  if (budget <= 0) return "";
  let out = "";
  let used = 0;
  for (const ch of text) {
    const w = textWidth(ch, fontSize);
    if (used + w > budget) break;
    out += ch;
    used += w;
  }
  return out === "" ? "" : out + ellipsis;
}

/**
 * 把「守位 → 顯示內容」映射攤成九個固定格位。未給的守位一律產出 `used: false` 的格位，
 * 不會消失——讀者要看得出哪些守位沒有資料。
 */
export function layoutCells(cells: FieldCells): LaidOutCell[] {
  return FIELD_POSITIONS.map((code) => {
    const slot = SLOTS[code];
    const content = cells[code];
    const used = content != null;
    const rawMeta = content?.meta?.trim() || null;
    const metaW = rawMeta ? META_W : 0;
    const maxW = slot.w - BADGE_W - metaW - PAD_X * 2;
    const main = fitText(content?.main?.trim() || POSITION_LABEL[code], maxW, MAIN_FONT);
    const rawSub = content?.sub?.trim();
    return {
      code,
      x: slot.x, y: slot.y, w: slot.w, h: CELL_H,
      cx: slot.x + slot.w / 2,
      contentCx: slot.x + BADGE_W + (slot.w - BADGE_W - metaW) / 2,
      main,
      sub: used && rawSub ? fitText(rawSub, maxW, SUB_FONT) : null,
      meta: used ? rawMeta : null,
      href: (used && content?.href) || null,
      used,
    };
  });
}

/** DH 不是守備位置；有資料時才在捕手右側追加，不污染球員守位分布圖。 */
export function layoutDesignatedHitter(content: FieldCellContent): LaidOutCell {
  const slot: Slot = { x: 248, y: 248, w: 100 };
  const rawMeta = content.meta?.trim() || null;
  const metaW = rawMeta ? META_W : 0;
  const maxW = slot.w - BADGE_W - metaW - PAD_X * 2;
  const rawSub = content.sub?.trim();
  return {
    code: "DH", x: slot.x, y: slot.y, w: slot.w, h: CELL_H,
    cx: slot.x + slot.w / 2,
    contentCx: slot.x + BADGE_W + (slot.w - BADGE_W - metaW) / 2,
    main: fitText(content.main?.trim() || "指定打擊", maxW, MAIN_FONT),
    sub: rawSub ? fitText(rawSub, maxW, SUB_FONT) : null,
    meta: rawMeta,
    href: content.href || null,
    used: true,
  };
}

/**
 * aria-label 敘述：讀出每個有資料的守位與副標，並點出無資料的守位數。
 * 顏色與位置不是唯一區辨手段（設計 Brief §可及性）。
 *
 * 刻意讀**未截斷**的原文：截斷是格子寬度的限制，語音沒有這個限制，
 * 跟著截只會讓螢幕閱讀器使用者拿到比視覺讀者更少的資訊。
 */
export function describeCells(cells: FieldCells, caption: string): string {
  const used = FIELD_POSITIONS.filter((code) => cells[code] != null);
  if (used.length === 0) return `${caption}：無守備位置資料`;
  const parts = used.map((code) => {
    const main = cells[code]?.main?.trim() || POSITION_LABEL[code];
    const sub = cells[code]?.sub?.trim();
    const meta = cells[code]?.meta?.trim();
    return `${main}${sub ? ` ${sub}` : ""}${meta ? ` 第${meta}棒` : ""}`;
  });
  const idle = FIELD_POSITIONS.length - used.length;
  const tail = idle > 0 ? `；其餘 ${idle} 個守位無資料` : "";
  return `${caption}：${parts.join("、")}${tail}`;
}
