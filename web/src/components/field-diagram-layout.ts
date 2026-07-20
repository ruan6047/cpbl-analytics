// 守備位置圖的純佈局邏輯（UI-FIELD-DIAGRAM1）。與 React 分離，才能以 node --test 測。
//
// 這張圖是「守位身分圖」，不宣稱空間精確度（見 docs/research/UX-PLAYER-FIELDVIZ1_RESEARCH.md §1）。
// 前一版以真實球場座標擺位，內野守位在小尺寸下彼此過近，標籤與副標必然相交（實測多守位每個
// 案例皆有重疊）。既然不需要真實座標，就沒有理由付出可讀性代價：改採轉播記分板慣用的制式格位
// ——外野三格一列、內野四格、投手、捕手，格位固定且互不相鄰，可讀性優先。

/** 守位鍵。與 `cpbl.game_livelog.defend_station_code` 的一軍實測值對齊，供賽況頁沿用。 */
export type FieldPosition = "LF" | "CF" | "RF" | "3B" | "SS" | "2B" | "1B" | "P" | "C";

/** 每格的顯示內容，由呼叫端決定；本元件不假設資料來源。 */
export type FieldCellContent = {
  /** 主標；省略時用守位中文名。 */
  main?: string;
  /** 副標（局數／場數／球員名等自由字串）；null 或省略即不顯示。 */
  sub?: string | null;
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

export const VIEW_W = 320;
export const VIEW_H = 218;
export const CELL_H = 38;
/** 文字左右內距（單邊）。 */
export const PAD_X = 6;
export const MAIN_FONT = 12;
export const SUB_FONT = 10;
/** 主標／副標基線相對格頂的位移。有副標時主標上移，讓兩行在格內視覺置中。 */
export const MAIN_BASELINE = 16;
export const MAIN_BASELINE_ALONE = 23;
export const SUB_BASELINE = 30;

type Slot = { x: number; y: number; w: number };

const SLOTS: Record<FieldPosition, Slot> = {
  // 外野列：三格一列
  LF: { x: 6, y: 6, w: 96 },
  CF: { x: 112, y: 6, w: 96 },
  RF: { x: 218, y: 6, w: 96 },
  // 內野列：四格。左右順序＝看台視角（三壘在左、一壘在右）
  "3B": { x: 4, y: 62, w: 72 },
  SS: { x: 84, y: 62, w: 72 },
  "2B": { x: 164, y: 62, w: 72 },
  "1B": { x: 244, y: 62, w: 72 },
  // 投手、捕手各自獨立一列，置中
  P: { x: 112, y: 118, w: 96 },
  C: { x: 112, y: 174, w: 96 },
};

export type LaidOutCell = {
  code: FieldPosition;
  x: number; y: number; w: number; h: number;
  /** 格中心 x，文字以此為 text-anchor="middle" 的錨點。 */
  cx: number;
  main: string;
  sub: string | null;
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
    const maxW = slot.w - PAD_X * 2;
    const main = fitText(content?.main?.trim() || POSITION_LABEL[code], maxW, MAIN_FONT);
    const rawSub = content?.sub?.trim();
    return {
      code,
      x: slot.x, y: slot.y, w: slot.w, h: CELL_H,
      cx: slot.x + slot.w / 2,
      main,
      sub: used && rawSub ? fitText(rawSub, maxW, SUB_FONT) : null,
      used,
    };
  });
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
    return sub ? `${main} ${sub}` : main;
  });
  const idle = FIELD_POSITIONS.length - used.length;
  const tail = idle > 0 ? `；其餘 ${idle} 個守位無資料` : "";
  return `${caption}：${parts.join("、")}${tail}`;
}
