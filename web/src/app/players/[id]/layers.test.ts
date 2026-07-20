import assert from "node:assert/strict";
import { test } from "node:test";
import {
  SPARSE_PITCHES, SUB_LAYERS, type DataGroup, needsData, roleFromParam, sparsePitchNote,
  subLayerFromParam, subLayerLabel,
} from "./layers.ts";

test("稀疏警示：有樣本但過少才出現，且帶球數與原因", () => {
  const note = sparsePitchNote(14);
  assert.ok(note && note.includes("14"), "應標出實際球數");
  assert.ok(note!.includes("僅供參考"), "應標示僅供參考");
  assert.ok(note!.includes("設備"), "應說明成因（球場設備覆蓋）");
  assert.equal(sparsePitchNote(SPARSE_PITCHES - 1) === null, false);
});

test("稀疏警示：樣本充足、全無樣本或未載入都不顯示", () => {
  assert.equal(sparsePitchNote(SPARSE_PITCHES), null);
  assert.equal(sparsePitchNote(848), null);
  assert.equal(sparsePitchNote(0), null);   // 無資料是空態的職責，不是稀疏
  assert.equal(sparsePitchNote(null), null); // 載入中不預告警示
  assert.equal(sparsePitchNote(undefined), null);
});

test("L2 標籤跟隨 role：打者=打法、投手=球路", () => {
  assert.equal(subLayerLabel("approach", "batting"), "打法");
  assert.equal(subLayerLabel("approach", "pitching"), "球路");
  // L3/L4 不隨 role 改字
  assert.equal(subLayerLabel("splits", "batting"), subLayerLabel("splits", "pitching"));
  assert.equal(subLayerLabel("career", "batting"), "生涯");
});

test("?sec= 合法值原樣採用", () => {
  for (const s of SUB_LAYERS) assert.equal(subLayerFromParam(s, false), s);
});

test("?sec= 非法或缺漏時：現役落打法／球路、退役落生涯", () => {
  assert.equal(subLayerFromParam(null, false), "approach");
  assert.equal(subLayerFromParam("overview", false), "approach"); // 總覽常駐，不是可切子層
  assert.equal(subLayerFromParam("../evil", false), "approach");
  assert.equal(subLayerFromParam(null, true), "career");
  // 退役者仍可主動進其他層（四層皆可及，只是預設不同）
  assert.equal(subLayerFromParam("approach", true), "approach");
});

test("?role= 只接受該球員實際具備的 role", () => {
  assert.equal(roleFromParam("pitching", ["batting", "pitching"], "batting"), "pitching");
  assert.equal(roleFromParam("pitching", ["batting"], "batting"), "batting"); // 純打者不得被 URL 切成投手
  assert.equal(roleFromParam(null, ["pitching"], "pitching"), "pitching");
  assert.equal(roleFromParam("coach", ["batting"], "batting"), "batting");
});

test("常駐資料群組在任一層都要載入", () => {
  const always: DataGroup[] = ["profile", "season", "advanced", "trend"];
  for (const g of always) {
    for (const layer of SUB_LAYERS) assert.equal(needsData(g, layer), true, `${g}@${layer}`);
  }
});

test("層專屬資料群組只在該層載入（避免首屏打完全部端點）", () => {
  assert.equal(needsData("tracking", "approach"), true);
  assert.equal(needsData("tracking", "splits"), false);
  assert.equal(needsData("movement", "career"), false);
  assert.equal(needsData("splits", "splits"), true);
  assert.equal(needsData("splits", "approach"), false);
  assert.equal(needsData("career", "career"), true);
  assert.equal(needsData("fielding", "career"), true);
  assert.equal(needsData("fielding", "approach"), false);
});

test("每個資料群組至多屬於一層，避免同一請求被兩層各抓一次", () => {
  const groups: DataGroup[] = [
    "profile", "season", "advanced", "trend", "tracking", "movement", "splits", "career", "fielding",
  ];
  for (const g of groups) {
    const owners = SUB_LAYERS.filter((l) => needsData(g, l));
    assert.ok(owners.length === 1 || owners.length === SUB_LAYERS.length,
      `${g} 應為單層專屬或常駐，實際 owners=${owners.join(",")}`);
  }
});
