// #201 對手交手隊別四態：判準落在畫出來的字，不落在原始碼形狀。
import assert from "node:assert/strict";
import test from "node:test";
import { renderToStaticMarkup } from "react-dom/server";

import OpponentTeamMark from "./opponent-team-mark.tsx";
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

test("本季／區間（API 無狀態欄）沿用官方隊號", () => {
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
