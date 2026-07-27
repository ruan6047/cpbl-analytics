import assert from "node:assert/strict";
import test from "node:test";

import {
  SEMANTICS_BADGE,
  TEAM_STYLE_COPY,
  TEAM_STYLE_SECTION,
  buildHistoryVM,
  clampZ,
  formatZ,
  managerRuns,
  outsToIp,
  tenurePaletteFrom,
  type TeamStyleAxisKey,
  type TeamStyleAxisValue,
} from "./team-style.ts";

// —— 掃描素材：把文案表 + 區塊文案的所有使用者可見字串攤平 ——

const sampleValue: TeamStyleAxisValue = {
  z: 1.23,
  raw: 0.106,
  league_raw_mean: 0.089,
  rank: 1,
  counts: { sb: 9, cs: 3, sh: 41, pa: 2654, extra_bases: 120, ab: 2300,
    bb: 250, so: 500, starter_outs: 1620, outs: 2916, so_a: 480, pa_against: 3200 },
};

const AXIS_KEYS = Object.keys(TEAM_STYLE_COPY) as TeamStyleAxisKey[];

function allCopyStrings(): { source: string; text: string }[] {
  const out: { source: string; text: string }[] = [];
  for (const key of AXIS_KEYS) {
    const c = TEAM_STYLE_COPY[key];
    out.push({ source: `${key}.desc`, text: c.desc });
    out.push({ source: `${key}.note`, text: c.note });
    out.push({ source: `${key}.detail`, text: c.detail(sampleValue) });
  }
  for (const badge of Object.values(SEMANTICS_BADGE)) {
    if (badge) out.push({ source: "badge", text: badge });
  }
  for (const [k, v] of Object.entries(TEAM_STYLE_SECTION)) {
    if (typeof v === "string") out.push({ source: `section.${k}`, text: v });
  }
  out.push({ source: "section.rankLabel", text: TEAM_STYLE_SECTION.rankLabel(3, 6) });
  out.push({ source: "section.managerMarkerLabel", text: TEAM_STYLE_SECTION.managerMarkerLabel("葉君璋", 2021, 2025) });
  out.push({ source: "section.inProgressNote", text: TEAM_STYLE_SECTION.inProgressNote([2026]) });
  return out;
}

// —— 約束 5：零預測性語言（全域禁用清單）——

const PREDICTIVE_BANNED = [
  "勝率", "勝場", "戰績", "賽果", "預測", "預期", "看好", "將會",
  "因此", "有利", "贏球", "勝出", "領先聯盟",
];

test("約束5：全部文案零預測性語言", () => {
  for (const { source, text } of allCopyStrings()) {
    for (const banned of PREDICTIVE_BANNED) {
      assert.ok(!text.includes(banned), `${source} 含預測性詞彙「${banned}」：${text}`);
    }
  }
});

// —— 文案紅線：不用隊伍非官方暱稱 ——

const FAN_NICKNAMES = ["龍龍", "爪爪", "喵喵", "邦邦", "吱吱", "啾啾"];

test("文案紅線：不用隊伍非官方暱稱", () => {
  for (const { source, text } of allCopyStrings()) {
    for (const nick of FAN_NICKNAMES) {
      assert.ok(!text.includes(nick), `${source} 含非官方暱稱「${nick}」`);
    }
  }
});

// —— 約束 3：守備效率列零形容詞（只有數字與排名）——

const STYLE_ADJECTIVES = [
  "型", "風格", "傾向", "擅長", "穩定", "優異", "紮實", "出色",
  "強", "弱", "佳", "差", "好", "壞", "鐵壁", "銅牆",
];

test("約束3：守備效率 desc/note 為空、detail 僅數字", () => {
  const d = TEAM_STYLE_COPY.defense;
  assert.equal(d.desc, "");
  assert.equal(d.note, "");
  const detail = d.detail(sampleValue);
  for (const adj of STYLE_ADJECTIVES) {
    assert.ok(!detail.includes(adj), `defense.detail 含形容詞「${adj}」：${detail}`);
  }
  assert.match(detail, /^DER [.\d—]+$/, `defense.detail 應只有 DER 數字：${detail}`);
});

test("約束3：守備效率 semantics=numbers_only 不掛任何徽章", () => {
  assert.equal(SEMANTICS_BADGE.numbers_only, null);
});

// —— 約束 3：先發吃局／三振型投手標「本季」；選球紀律可標跨季延續 ——

test("約束3：current_season_only 徽章文案＝「本季」", () => {
  assert.equal(SEMANTICS_BADGE.current_season_only, "本季");
  assert.ok(TEAM_STYLE_COPY.starter_ip.note.includes("跨季不延續"));
  assert.ok(TEAM_STYLE_COPY.pitch_k.note.includes("跨季不延續"));
});

test("約束3：唯一可標「具跨季延續性」的是 cross_season_stable（選球紀律）", () => {
  assert.equal(SEMANTICS_BADGE.cross_season_stable, "具跨季延續性");
  // 「跨季延續性」正面宣稱不得出現在其他軸的文案（speed 的「跨季延續偏弱」是弱化語意，允許）
  for (const key of AXIS_KEYS.filter((k) => k !== "discipline")) {
    const c = TEAM_STYLE_COPY[key];
    for (const text of [c.desc, c.note]) {
      assert.ok(!text.includes("具跨季延續"), `${key} 不得宣稱跨季延續性：${text}`);
    }
  }
});

// —— 約束 7：全季口徑明示「全年」；約束 8：進行中賽季標注 ——

test("約束7：區塊明示全年口徑", () => {
  assert.equal(TEAM_STYLE_SECTION.scopeBadge, "全年");
});

test("約束8：賽季進行中標注文案", () => {
  assert.equal(TEAM_STYLE_SECTION.inProgressBadge, "賽季進行中");
  assert.ok(TEAM_STYLE_SECTION.inProgressNote([2026]).includes("2026"));
});

// —— 約束 2：教練名僅時間標記，不得暗示「時期風格」——

const ERA_STYLE_BANNED = ["時期風格", "時代", "體系", "作風", "帶隊風格"];

test("約束2：教練相關文案不暗示時期風格", () => {
  for (const { source, text } of allCopyStrings()) {
    for (const banned of ERA_STYLE_BANNED) {
      assert.ok(!text.includes(banned), `${source} 含時期風格暗示「${banned}」：${text}`);
    }
  }
  assert.ok(TEAM_STYLE_SECTION.managerFootnote.includes("僅作時間標記"));
});

test("教練標記格式＝閉區間「名 起–迄」；單季不重複年份", () => {
  assert.equal(TEAM_STYLE_SECTION.managerMarkerLabel("陳金鋒", 2024, 2025), "陳金鋒 2024–2025");
  assert.equal(TEAM_STYLE_SECTION.managerMarkerLabel("洪一中", 2020, 2020), "洪一中 2020");
});

// —— managerRuns：任期段（閉區間）導出 ——

test("managerRuns：換帥開新段；迄年＝該段最後判定季，不延伸到未判定季", () => {
  // AEO011 實例尾段：資料只判定到 2025，2026 未判定 → 陳金鋒段止於 2025
  const ms = managerRuns([
    { year: 2020, manager: "洪一中" },
    { year: 2021, manager: "洪一中" },
    { year: 2022, manager: "丘昌榮" },
    { year: 2023, manager: "丘昌榮" },
    { year: 2024, manager: "陳金鋒" },
    { year: 2025, manager: "陳金鋒" },
    { year: 2026, manager: null },
  ]);
  assert.deepEqual(ms, [
    { name: "洪一中", from: 2020, to: 2021 },
    { name: "丘昌榮", from: 2022, to: 2023 },
    { name: "陳金鋒", from: 2024, to: 2025 },
  ]);
});

test("managerRuns：不可判定季跳過不斷開；同名跨未知季視為同段", () => {
  // ADD011 實例：2018 黃甘霖 → 2019 不可判定 → 2020 林岳平
  const ms = managerRuns([
    { year: 2018, manager: "黃甘霖" },
    { year: 2019, manager: null },
    { year: 2020, manager: "林岳平" },
  ]);
  assert.deepEqual(ms, [
    { name: "黃甘霖", from: 2018, to: 2018 },
    { name: "林岳平", from: 2020, to: 2020 },
  ]);
  // 同名跨過未知季不斷開（未知季無從宣稱換帥），段延伸到最後判定季
  const same = managerRuns([
    { year: 2021, manager: "葉君璋" },
    { year: 2022, manager: null },
    { year: 2023, manager: "葉君璋" },
  ]);
  assert.deepEqual(same, [{ name: "葉君璋", from: 2021, to: 2023 }]);
});

test("managerRuns：亂序輸入照年份排序", () => {
  const ms = managerRuns([
    { year: 2024, manager: "平野惠一" },
    { year: 2021, manager: "林威助" },
    { year: 2025, manager: "平野惠一" },
  ]);
  assert.deepEqual(ms, [
    { name: "林威助", from: 2021, to: 2021 },
    { name: "平野惠一", from: 2024, to: 2025 },
  ]);
});

// —— 歷史逐季：raw 模式與 discipline 退回 z（需求方 2026-07-27 續審裁定）——

test("歷史圖：六個單成分軸有 formatRaw；discipline 複合軸無（退回 z）", () => {
  for (const key of AXIS_KEYS.filter((k) => k !== "discipline")) {
    assert.equal(typeof TEAM_STYLE_COPY[key].formatRaw, "function",
      `${key} 應有 formatRaw（歷史圖畫原始值）`);
  }
  assert.equal(TEAM_STYLE_COPY.discipline.formatRaw, undefined);
  // 率值格式抽樣：% 軸一位小數、比值軸三位小數去前導零
  assert.equal(TEAM_STYLE_COPY.smallball.formatRaw?.(0.0154), "1.5%");
  assert.equal(TEAM_STYLE_COPY.defense.formatRaw?.(0.7003), ".700");
  assert.equal(TEAM_STYLE_COPY.power.formatRaw?.(0.086), ".086");
});

test("歷史圖文案：raw 模式標明聯盟平均參照；z 退回模式說明複合軸", () => {
  assert.ok(TEAM_STYLE_SECTION.historyCaption.includes("聯盟平均"));
  assert.ok(TEAM_STYLE_SECTION.historyCaptionZ.includes("複合軸"));
  assert.equal(TEAM_STYLE_SECTION.legendLeague, "聯盟平均");
});

// —— 歷史圖聯盟基準契約（第四批回歸修復：均線不得靜默消失）——

const makeSeason = (year: number, overrides: Partial<TeamStyleAxisValue> = {}) => {
  const axes = Object.fromEntries(AXIS_KEYS.map((k) => [k, {
    ...sampleValue,
    raw: k === "discipline" ? null : sampleValue.raw,
    league_raw_mean: k === "discipline" ? null : sampleValue.league_raw_mean,
    ...overrides,
  }])) as Record<TeamStyleAxisKey, TeamStyleAxisValue>;
  return { year, team_code: "AJL011", team_name: "樂天桃猿", n_teams: 6,
    in_progress: false, manager: null, axes };
};

test("歷史VM：每一軸恰有一種聯盟基準（raw=均線序列／z=標示 y=0 基準線）", () => {
  const seasons = [makeSeason(2024), makeSeason(2025)];
  for (const key of AXIS_KEYS) {
    const vm = buildHistoryVM(key, seasons);
    assert.equal(vm.leagueSeries !== vm.zeroBaseline, true,
      `${key} 必須恰有一種聯盟基準呈現`);
    assert.equal(vm.baselineLabel, "聯盟平均");
    if (key === "discipline") {
      assert.equal(vm.mode, "z");
      assert.ok(vm.zeroBaseline, "discipline 退回 z 須有標示的 y=0 基準線");
    } else {
      assert.equal(vm.mode, "raw");
      assert.ok(vm.leagueSeries, `${key} raw 模式須渲染聯盟平均序列`);
      // 均線序列的值＝API 的 league_raw_mean（不得另算）
      for (const p of vm.points) assert.equal(p.league, p.v.league_raw_mean);
    }
  }
});

test("歷史VM：z 退回模式不帶 league 序列值；點含 tooltip 所需欄位", () => {
  const vm = buildHistoryVM("discipline", [makeSeason(2024)]);
  assert.equal(vm.points[0].league, null);
  assert.equal(vm.points[0].value, vm.points[0].v.z);
  assert.equal(vm.points[0].n_teams, 6);
});

// —— 任期色盤：跳過 chart-1（資料線）與 chart-6（中性灰＝參考元素保留）——

test("任期色盤：扣 chart-1 與 chart-6 後輪替；相鄰任期不同色", () => {
  const series = ["c1", "c2", "c3", "c4", "c5", "c6", "c7", "c8"];
  const pal = tenurePaletteFrom(series);
  assert.deepEqual(pal, ["c2", "c3", "c4", "c5", "c7", "c8"]);
  assert.ok(!pal.includes("c1"), "chart-1 保留給資料折線");
  assert.ok(!pal.includes("c6"), "chart-6 中性灰保留給聯盟均線等參考元素");
  // 樂天活證據：2025 古久保健二 → 2026 曾豪駒為兩段（不得延伸前任），色帶不同
  const runs = managerRuns([
    { year: 2024, manager: "古久保健二" },
    { year: 2025, manager: "古久保健二" },
    { year: 2026, manager: "曾豪駒" },
  ]);
  assert.deepEqual(runs, [
    { name: "古久保健二", from: 2024, to: 2025 },
    { name: "曾豪駒", from: 2026, to: 2026 },
  ]);
  assert.notEqual(pal[0 % pal.length], pal[1 % pal.length]);
});

test("現任開區間 chip：任期止於進行中賽季 →「名 起–」", () => {
  assert.equal(TEAM_STYLE_SECTION.managerMarkerLabelOpen("曾豪駒", 2026), "曾豪駒 2026–");
  assert.equal(TEAM_STYLE_SECTION.managerMarkerLabelOpen("葉君璋", 2021), "葉君璋 2021–");
});

// —— 純格式化 ——

test("formatZ／clampZ／outsToIp", () => {
  assert.equal(formatZ(1.234), "+1.23");
  assert.equal(formatZ(-0.5), "-0.50");
  assert.equal(formatZ(0), "+0.00");
  assert.equal(clampZ(2.4), 2);
  assert.equal(clampZ(-3), -2);
  assert.equal(clampZ(0.7), 0.7);
  assert.equal(outsToIp(540), "180");
  assert.equal(outsToIp(542), "180.2");
  assert.equal(outsToIp(0), "0");
});

// —— 明細文案抽樣（次數＋排名導向，對齊約束 1 範例「短打 38 次，聯盟第 1」）——

test("約束1：明細給原始次數；排名文案格式", () => {
  assert.ok(TEAM_STYLE_COPY.smallball.detail(sampleValue).includes("犧短 41 次"));
  assert.ok(TEAM_STYLE_COPY.speed.detail(sampleValue).includes("盜壘企圖 12 次"));
  assert.equal(TEAM_STYLE_SECTION.rankLabel(1, 6), "聯盟第 1（/6 隊）");
});
