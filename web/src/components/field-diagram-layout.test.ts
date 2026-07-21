import assert from "node:assert/strict";
import { test } from "node:test";
import {
  BADGE_W, CELL_H, FIELD_POSITIONS, MAIN_FONT, PAD_X, POSITION_LABEL, SUB_FONT,
  type FieldCells, describeCells, fitText, layoutCells, layoutDesignatedHitter, textWidth,
} from "./field-diagram-layout.ts";

// ---- 格位映射 ----

test("九個守位一律產出格位，順序為由上而下的閱讀順序", () => {
  const laid = layoutCells({});
  assert.equal(laid.length, 9);
  assert.deepEqual(laid.map((c) => c.code), FIELD_POSITIONS);
});

test("有資料的守位 used=true，未給的守位 used=false 但仍佔格（不得消失）", () => {
  const laid = layoutCells({ SS: { sub: "640 局" }, "2B": { sub: "120 局" } });
  const used = laid.filter((c) => c.used).map((c) => c.code);
  assert.deepEqual(used, ["SS", "2B"]);
  assert.equal(laid.length, 9, "未使用格位必須保留，讀者要看得出哪些守位沒有資料");
  const idle = laid.find((c) => c.code === "LF")!;
  assert.equal(idle.used, false);
  assert.equal(idle.main, POSITION_LABEL.LF, "未使用格位仍標出守位名");
  assert.equal(idle.sub, null);
});

test("主標預設為守位中文名，可由呼叫端覆寫", () => {
  const laid = layoutCells({ P: {}, C: { main: "捕" } });
  assert.equal(laid.find((c) => c.code === "P")!.main, "投手");
  assert.equal(laid.find((c) => c.code === "C")!.main, "捕");
});

test("棒次 meta 保留在右側短標，並壓縮主標可用寬度", () => {
  const cell = layoutCells({ CF: { main: "超過四個字的名字", meta: "1" } }).find((c) => c.code === "CF")!;
  assert.equal(cell.meta, "1");
  assert.ok(cell.main.endsWith("…"));
});

test("DH 只在呼叫端提供時追加於捕手旁，不混入九個守備位置", () => {
  assert.equal(layoutCells({}).length, 9);
  const dh = layoutDesignatedHitter({ main: "蘇智傑", meta: "4" });
  assert.equal(dh.code, "DH");
  assert.equal(dh.main, "蘇智傑");
  assert.equal(dh.meta, "4");
  assert.ok(dh.x > layoutCells({}).find((c) => c.code === "C")!.x);
});

// ---- 副標缺值 ----

test("副標缺值（未給／null／空白）一律不顯示，但格位仍算有資料", () => {
  const cells: FieldCells = { LF: {}, CF: { sub: null }, RF: { sub: "   " } };
  const laid = layoutCells(cells);
  for (const code of ["LF", "CF", "RF"] as const) {
    const c = laid.find((x) => x.code === code)!;
    assert.equal(c.sub, null, `${code} 副標應為 null`);
    assert.equal(c.used, true, `${code} 仍應算有資料`);
  }
});

test("未使用格位不吃副標（避免呼叫端誤傳造成無資料格出現數字）", () => {
  const laid = layoutCells({});
  assert.ok(laid.every((c) => c.sub === null));
});

// ---- 不相交的必要條件：格位矩形互不重疊、文字截斷於格內 ----

test("任兩個格位矩形不相交", () => {
  const laid = layoutCells({});
  for (let i = 0; i < laid.length; i += 1) {
    for (let j = i + 1; j < laid.length; j += 1) {
      const a = laid[i], b = laid[j];
      const overlap = a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + a.h && b.y < a.y + a.h;
      assert.equal(overlap, false, `${a.code} 與 ${b.code} 的格位相交`);
    }
  }
  assert.ok(laid.every((c) => c.h === CELL_H));
});

test("主標與副標估寬後皆不超出格內可用寬度（含滿守位）", () => {
  const cells = Object.fromEntries(
    FIELD_POSITIONS.map((p) => [p, { sub: "999 局" }]),
  ) as FieldCells;
  for (const c of layoutCells(cells)) {
    const maxW = c.w - BADGE_W - PAD_X * 2;
    assert.ok(textWidth(c.main, MAIN_FONT) <= maxW, `${c.code} 主標超寬`);
    assert.ok(textWidth(c.sub ?? "", SUB_FONT) <= maxW, `${c.code} 副標超寬`);
  }
});

test("過長副標被截斷並以 … 結尾，仍不超寬", () => {
  const laid = layoutCells({ "3B": { sub: "王柏融、林立、陳子豪" } });
  const c = laid.find((x) => x.code === "3B")!;
  assert.ok(c.sub!.endsWith("…"), "應截斷");
  assert.ok(textWidth(c.sub!, SUB_FONT) <= c.w - BADGE_W - PAD_X * 2);
});

test("fitText：容得下就原樣返回；容不下任何字元回空字串", () => {
  assert.equal(fitText("投手", 100, 12), "投手");
  assert.equal(fitText("投手", 2, 12), "");
});

test("textWidth：半形約 0.6em、全形約 1em", () => {
  assert.equal(textWidth("ab", 10), 12);
  assert.equal(textWidth("投手", 10), 20);
});

// ---- aria-label ----

test("aria-label 讀出每個有資料的守位與副標，並點出無資料守位數", () => {
  const label = describeCells({ SS: { sub: "640 局" }, "2B": { sub: "120 局" } }, "守位分布");
  assert.equal(label, "守位分布：游擊 640 局、二壘 120 局；其餘 7 個守位無資料");
});

test("aria-label：無副標時只讀守位名；滿守位時不加無資料註記", () => {
  assert.equal(describeCells({ P: {} }, "守位分布"), "守位分布：投手；其餘 8 個守位無資料");
  const all = Object.fromEntries(FIELD_POSITIONS.map((p) => [p, {}])) as FieldCells;
  assert.equal(describeCells(all, "先發守備"), `先發守備：${FIELD_POSITIONS.map((p) => POSITION_LABEL[p]).join("、")}`);
});

test("aria-label：完全無資料時明說無資料，不產出空敘述", () => {
  assert.equal(describeCells({}, "守位分布"), "守位分布：無守備位置資料");
});

test("aria-label 讀未截斷原文——語音無寬度限制，不該比視覺讀者拿到更少資訊", () => {
  const long = "王柏融、林立、陳子豪";
  assert.ok(layoutCells({ SS: { sub: long } })[4].sub!.endsWith("…"), "視覺上確實被截斷");
  assert.ok(describeCells({ SS: { sub: long } }, "守位分布").includes(long));
});
