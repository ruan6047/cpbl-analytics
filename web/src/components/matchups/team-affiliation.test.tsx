// #201 對手交手隊別四態：判準落在畫出來的字，不落在原始碼形狀。
import assert from "node:assert/strict";
import test from "node:test";
import { renderToStaticMarkup } from "react-dom/server";

import type { PairDetail, PairRow } from "./api.ts";
import OpponentTeamMark from "./opponent-team-mark.tsx";
import PairCard from "./pair-card.tsx";
import { rowFranchises, teamAffiliation } from "./team-affiliation.ts";

test("四態：已確認單隊只畫隊徽、多隊／部分可證附說明、未知不畫隊徽", () => {
  assert.deepEqual(teamAffiliation("confirmed", ["ACN011"], "AJL011"), { codes: ["ACN011"], note: null });
  assert.deepEqual(teamAffiliation("confirmed", ["ACN011", "AKP011"], null), {
    codes: ["ACN011", "AKP011"],
    note: "多隊",
  });
  assert.deepEqual(teamAffiliation("partial", ["AEO011"], null), { codes: ["AEO011"], note: "其餘未知" });
  // 未知時不得退回官方現任隊號（那正是 #201 的錯標來源）。
  assert.deepEqual(teamAffiliation("unknown", [], "AJL011"), { codes: [], note: "隊別未知" });
});

test("本季／區間與生涯非首批（API 無狀態欄）沿用官方隊號", () => {
  assert.deepEqual(teamAffiliation(undefined, undefined, "AJL011"), { codes: ["AJL011"], note: null });
  assert.deepEqual(rowFranchises({ opp_franchise: "AJL011" }), ["AJL011"]);
  assert.deepEqual(rowFranchises({ opp_franchise: null }), []);
});

test("下拉可選隊別：生涯取已證實集合，不取官方隊號", () => {
  assert.deepEqual(rowFranchises({ opp_franchises: ["ACN011", "AKP011"], opp_franchise: null }), [
    "ACN011",
    "AKP011",
  ]);
  assert.deepEqual(rowFranchises({ opp_franchises: [], opp_franchise: null }), []);
});

test("渲染：未知只出現文字、部分可證同時有隊徽與「其餘未知」", () => {
  const unknown = renderToStaticMarkup(
    <OpponentTeamMark status="unknown" franchises={[]} fallbackCode="AJL011" />,
  );
  assert.match(unknown, /隊別未知/);
  assert.doesNotMatch(unknown, /aria-hidden/, "未知不得畫任何隊徽");

  const partial = renderToStaticMarkup(
    <OpponentTeamMark status="partial" franchises={["AEO011"]} fallbackCode="AJL011" />,
  );
  assert.match(partial, /其餘未知/);
  assert.equal((partial.match(/aria-hidden/g) ?? []).length, 1);

  const multi = renderToStaticMarkup(
    <OpponentTeamMark status="confirmed" franchises={["ACN011", "AKP011"]} />,
  );
  assert.match(multi, /多隊/);
  assert.equal((multi.match(/aria-hidden/g) ?? []).length, 2);

  const single = renderToStaticMarkup(<OpponentTeamMark status="confirmed" franchises={["ACN011"]} />);
  assert.doesNotMatch(single, /多隊|其餘未知|隊別未知/);
});

test("生涯混合清單：首批取證據、非首批取官方隊號，下拉集合為兩者聯集", () => {
  const rows = [
    // 林立 × 陳鴻文（首批）：富邦 36＋2017 中信 5。
    { opp_franchises: ["ACN011", "AEO011"], opp_team_status: "confirmed" as const, opp_franchise: null },
    // 非首批：API 不帶證據欄，官方隊號照舊。
    { opp_franchise: "AJL011" },
  ];
  assert.deepEqual(rows.map(rowFranchises), [["ACN011", "AEO011"], ["AJL011"]]);
  const plain = renderToStaticMarkup(<OpponentTeamMark fallbackCode="AJL011" />);
  assert.doesNotMatch(plain, /多隊|其餘未知|隊別未知/, "非首批不得出現證據說明");
  assert.equal((plain.match(/aria-hidden/g) ?? []).length, 1);
});

test("單組對決卡：首批對手側與清單同判定；非首批兩側照舊官方隊號", () => {
  const base = {
    kind_code: "A" as const,
    hitter_name: "林立",
    pitcher_name: "陳鴻文",
    hitter_team_code: "AJL011",
    pitcher_team_code: "AJL011",
    hitter_franchise: "AJL011",
    pitcher_franchise: "AJL011",
    plate_appearances: 41,
  } as unknown as PairRow;
  const render = (row: PairRow, role: "batting" | "pitching") =>
    renderToStaticMarkup(
      <PairCard
        data={
          {
            hitter: "0000002286",
            pitcher: "0000003606",
            kind_code: null,
            scope: "career",
            from_year: 1990,
            to_year: 2026,
            coverage: { career: true, annual_years: [] },
            items: [row],
          } as PairDetail
        }
        role={role}
        scopeLabel="生涯"
        kind="A"
      />,
    );
  const first = {
    ...base,
    pitcher_franchises: ["ACN011", "AEO011"],
    pitcher_team_status: "confirmed",
    hitter_franchises: ["AJL011"],
    hitter_team_status: "confirmed",
  } as PairRow;
  assert.match(render(first, "batting"), /多隊/);
  assert.doesNotMatch(render(first, "pitching"), /多隊|其餘未知|隊別未知/);
  for (const role of ["batting", "pitching"] as const) {
    assert.doesNotMatch(render(base, role), /多隊|其餘未知|隊別未知/);
  }
});
