import assert from "node:assert/strict";
import { test } from "node:test";
import {
  POS_COORD, innings, isMultiPosition, isQualified, per9, posGroup, posLabel, primaryPos,
  valueMetrics, vizRows,
} from "./fielding-metrics.ts";

// REVIEW-005 P0 回歸：二軍守備資料不得進入身分圖與價值卡
const farmSeason = [{ pos: "游擊手", g: 12 }, { pos: "二壘手", g: 5 }];
const firstTeamCareer = [{ pos: "中外野手", g: 200 }];

test("二軍鏡頭：不得使用本季（二軍）守備列，改用一軍生涯列", () => {
  const r = vizRows(farmSeason, firstTeamCareer, true);
  assert.deepEqual(r.map, firstTeamCareer);
  assert.equal(r.usesSeason, false, "二軍鏡頭下不得標記為使用本季列（價值卡據此不渲染）");
  assert.ok(!r.map.some((x) => x.pos === "游擊手"), "二軍守位不得出現在身分圖");
});

test("一軍鏡頭：正常使用本季守備列", () => {
  const r = vizRows([{ pos: "游擊手", g: 60 }], firstTeamCareer, false);
  assert.equal(r.usesSeason, true);
  assert.equal(r.map[0].pos, "游擊手");
});

test("二軍球員若無一軍生涯列 → 兩個元件都沒有資料可畫", () => {
  const r = vizRows(farmSeason, [], true);
  assert.deepEqual(r.map, []);
  assert.equal(r.usesSeason, false);
});

test("一軍但本季無守備（退役）→ 退回生涯列做身分描述", () => {
  const r = vizRows([], firstTeamCareer, false);
  assert.deepEqual(r.map, firstTeamCareer);
  assert.equal(r.usesSeason, false);
});

test("每 9 局率以局數為分母，不接受出賽數代替", () => {
  // 27 個出局＝9 局；10 次助殺 / 9 局 → 10.0
  assert.equal(per9(10, 27), 10);
  // 496 局的中外野手 2 次助殺 → 每 9 局 0.036
  assert.ok(Math.abs(per9(2, 1489)! - 0.036) < 0.001);
});

test("無局數（2018 前）或局數為 0 時不算率，回 null", () => {
  assert.equal(per9(10, null), null);      // 官方 fielding_seasons 無局數欄位
  assert.equal(per9(10, undefined), null);
  assert.equal(per9(10, 0), null);
  assert.equal(per9(null, 300), null);
});

test("局數換算與 null 傳遞", () => {
  assert.equal(innings(300), 100);
  assert.equal(innings(null), null);
});

test("合格門檻：300 outs（100 局）以上才進聯盟對照", () => {
  assert.equal(isQualified(300, 300), true);
  assert.equal(isQualified(299, 300), false);
  assert.equal(isQualified(null, 300), false); // 2018 前無局數 → 不可能合格
});

test("守位分群決定呈現內容", () => {
  assert.equal(posGroup("中外野手"), "outfield");
  assert.equal(posGroup("游擊手"), "infield");
  assert.equal(posGroup("一壘手"), "first");
  assert.equal(posGroup("捕手"), "catcher");
  assert.equal(posGroup("投手"), "pitcher");
  assert.equal(posGroup("指定打擊"), "other"); // DH 不在守備資料，落 other
});

test("一壘與投手不做價值宣稱（空指標集）", () => {
  assert.deepEqual(valueMetrics("first"), []);
  assert.deepEqual(valueMetrics("pitcher"), []);
  assert.deepEqual(valueMetrics("outfield"), ["a9"]);
  assert.ok(valueMetrics("infield").includes("dp9"));
});

test("多守位判定只算真正上場過的守位", () => {
  assert.equal(isMultiPosition([{ pos: "游擊手", g: 9 }, { pos: "三壘手", g: 3 }]), true);
  assert.equal(isMultiPosition([{ pos: "中外野手", g: 68 }]), false);
  // 有紀錄列但出賽 0 不算一個守位
  assert.equal(isMultiPosition([{ pos: "游擊手", g: 9 }, { pos: "投手", g: 0 }]), false);
});

test("主守位取出賽最多者；並列或全空回 null 不硬選", () => {
  assert.equal(primaryPos([{ pos: "游擊手", g: 9 }, { pos: "三壘手", g: 3 }]), "游擊手");
  assert.equal(primaryPos([{ pos: "游擊手", g: 5 }, { pos: "三壘手", g: 5 }]), null);
  assert.equal(primaryPos([{ pos: "游擊手", g: 0 }]), null);
  assert.equal(primaryPos([]), null);
});

test("身分圖標籤：有局數用局數，2018 前退回場數", () => {
  assert.equal(posLabel(1489, 68), "496 局");
  assert.equal(posLabel(null, 68), "68 場");
  assert.equal(posLabel(null, null), "—");
});

test("九個守位都有座標，且左右半場方向正確", () => {
  for (const p of ["投手", "捕手", "一壘手", "二壘手", "三壘手", "游擊手", "左外野手", "中外野手", "右外野手"]) {
    assert.ok(POS_COORD[p], `${p} 缺座標`);
  }
  assert.ok(POS_COORD["左外野手"].deg < 0, "左外野應在負角度側");
  assert.ok(POS_COORD["右外野手"].deg > 0, "右外野應在正角度側");
  assert.ok(POS_COORD["中外野手"].dist > POS_COORD["游擊手"].dist, "外野應比內野遠");
});
