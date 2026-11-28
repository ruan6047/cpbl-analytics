import assert from "node:assert/strict";
import test from "node:test";
import type { ReactElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import {
  StaffChampionshipTag,
  StaffChampionshipsSection,
  staffChampionshipYears,
  type StaffChampionships,
} from "./staff-championships.tsx";

// #470：值取自資料檔 2023 味全龍列（張泰山 打擊教練、兩來源；王昊 單一來源）。
const DATA: StaffChampionships = {
  through_year: 2025,
  note: "名單不保證完整",
  missing_years: [],
  items: [
    {
      year: 2023, team_code: "AAA011", team_name: "味全龍", level: "一軍", title: "打擊教練",
      single_source: false, note: null,
      sources: [
        { site: "twbsball", label: "台灣棒球維基館", url: "https://twbsball.dils.tku.edu.tw/wiki/index.php/x" },
        { site: "zhwiki", label: "中文維基百科", url: "https://zh.wikipedia.org/wiki/y" },
      ],
    },
  ],
};

function text(node: ReactElement): string {
  return renderToStaticMarkup(node).replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim();
}

test("tag counts distinct years and stays separate from 總冠軍", () => {
  assert.equal(text(<StaffChampionshipTag data={DATA} />), "教練團冠軍 ×1");
  const two = { ...DATA, items: [...DATA.items, { ...DATA.items[0], level: "二軍" }] };
  assert.deepEqual(staffChampionshipYears(two), [2023]);
  assert.equal(renderToStaticMarkup(<StaffChampionshipTag data={null} />), "");
});

test("section shows row, level, title, sources and through-year note", () => {
  const t = text(<StaffChampionshipsSection data={DATA} heading={<h2>教練團奪冠</h2>} />);
  assert.match(t, /教練團奪冠/);
  assert.match(t, /2023 味全龍 一軍 打擊教練 台灣棒球維基館 中文維基百科/);
  assert.match(t, /不計入總冠軍次數/);
  assert.match(t, /資料截至 2025 年/);
  assert.doesNotMatch(t, /單一來源/);
  assert.doesNotMatch(t, /沒有教練團名單/);
});

test("single source flagged and missing years listed", () => {
  const d: StaffChampionships = {
    ...DATA,
    missing_years: [1994],
    items: [{ ...DATA.items[0], title: null, single_source: true, sources: [DATA.items[0].sources[0]] }],
  };
  const t = text(<StaffChampionshipsSection data={d} heading={<h2>h</h2>} />);
  assert.match(t, /單一來源/);
  assert.match(t, /一軍 — 台灣棒球維基館/);
  assert.match(t, /以下冠軍隊年來源沒有教練團名單：1994/);
});

test("renders nothing without items", () => {
  assert.equal(renderToStaticMarkup(<StaffChampionshipsSection data={{ ...DATA, items: [] }} heading="h" />), "");
});
