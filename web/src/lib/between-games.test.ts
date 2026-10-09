import assert from "node:assert/strict";
import { test } from "node:test";
import { loadReport, recapReportLink, reportJourney, reportLink, reportTab } from "./between-games.ts";
import { ApiError } from "./http-error.ts";
import type { Report, ReportKind } from "./report-types.ts";

const L="ADD011", B="ACN011", D="AAA011";
export function fixture(kind: ReportKind="E", wins=1): Report {
  const games = Array.from({length:wins},(_,i)=>({game_no:i+1,game_sno:i+1,date:`2026-10-${9+i}`,home_code:B,home_score:1,away_code:L,away_score:3}));
  return {status:"ok",season:2026,kind_code:kind,game_sno:wins,game:{year:2026,kind_code:kind,game_sno:wins,game_date:`2026-10-${9+wins-1}`,away_team_code:L,home_team_code:B,away_score:3,home_score:1,venue:"洲際"},
    journey_context:{summary:[{kind_code:"E",team1_code:L,team2_code:B,games}],
      rows:[2,3,4].map(sno=>({year:2026,kind_code:"E",game_sno:sno,game_date:`2026-10-${8+sno}`,away_team_code:sno===2?B:L,home_team_code:sno===2?L:B,away_score:99,home_score:0,completed:false,venue:"洲際"})),sources:[],context_hash:"a".repeat(64),cutoff_date:`2026-10-${8+wins}`,through_game_keys:[],order_consistent:true},players:[],population:[],sources:[],teams:[],watch_points:[]};
}
test("頁籤入口固定 X、年度與賽別；無效 tab 回總覽",()=>{
  for(const tab of ["overview","pitchers","fielders"] as const) assert.equal(reportLink(1,"E",2026,tab),`/games/1/report?kind=E&year=2026&tab=${tab}`);
  assert.equal(reportTab("invalid"),"overview");
});
test("賽況入口只在有年度的完賽 E/C 出現",()=>{
  assert.equal(recapReportLink(true,"1","E",2026),reportLink(1,"E",2026));
  assert.equal(recapReportLink(true,"1","C",2026),reportLink(1,"C",2026));
  assert.equal(recapReportLink(false,"1","E",2026),null);
  assert.equal(recapReportLink(true,"1","A",2026),null);
  assert.equal(recapReportLink(true,"1","E",undefined),null);
});
test("未完成列的比分清除；完賽後來 Y 不污染 X",()=>{
  const base=fixture();const next=reportJourney(base)?.next;
  assert.equal(next?.key,"E2");assert.equal(next?.score,null);
  const later=structuredClone(base);later.journey_context!.rows[0].completed=true;
  assert.equal(reportJourney(later)?.next?.key,"E2");
});
test("E 決勝後跳過已有條件 DB 列到 C，公告沒有正式 sno 不造 ID",()=>{
  const j=reportJourney(fixture("E",3));
  assert.equal(j?.series.E.tally.winner,L);assert.equal(j?.next?.key,"C1");assert.equal(j?.next?.row,null);
});
test("C 結束沒有下一場",()=>{
  const base=fixture("C",3);base.journey_context!.cutoff_date="2026-10-21";
  base.journey_context!.summary.push({kind_code:"C",team1_code:L,team2_code:D,games:Array.from({length:4},(_,i)=>({game_no:i+1,game_sno:i+1,date:`2026-10-${17+i}`,home_code:D,home_score:5,away_code:L,away_score:0}))});
  assert.equal(reportJourney(base)?.next,null);
});
test("兩次唯讀取數帶同 context，沒有正式場號只讀一次",async()=>{
  const calls:unknown[]=[];const result=await loadReport(async target=>{calls.push(target);return fixture();});
  assert.deepEqual(calls,[undefined,{kind:"E",sno:2,contextHash:"a".repeat(64)}]);assert.equal(result.updating,false);
  let n=0;await loadReport(async()=>{n++;return fixture("E",3);});assert.equal(n,1);
});
test("409 最多重做一次，第二次仍變更保留基礎且清除 next",async()=>{
  let n=0;const result=await loadReport(async target=>{n++;if(target)throw new ApiError("fixture",409);return fixture();});
  assert.equal(n,4);assert.equal(result.updating,true);assert.equal(result.report.next_game,null);
});
test("非 409 不自動重試",async()=>{
  let n=0;await assert.rejects(loadReport(async target=>{n++;if(target)throw new ApiError("fixture",422);return fixture();}));assert.equal(n,2);
});
