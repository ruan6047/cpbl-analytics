import assert from "node:assert/strict";
import { test } from "node:test";
import { loadReport, nextPreviewFor, nextPreviewLink, previewLink, previewMatches, recapReportLink, reportJourney, reportLink, reportTab } from "./between-games.ts";
import { ApiError } from "./http-error.ts";
import type { Report, ReportAnchor, ReportKind } from "./report-types.ts";

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
  assert.equal(recapReportLink(true,"1","E",2026),"/playoffs?year=2026&series=E&game=1#watch");
  assert.equal(recapReportLink(true,"1","C",2026),"/playoffs?year=2026&series=C&game=1#watch");
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
test("第一讀只取 context；有正式 Y 才帶 Y，無 Y 也帶同 context 做唯一完整讀",async()=>{
  const calls:unknown[]=[];const result=await loadReport(async request=>{calls.push(request);return fixture();});
  assert.deepEqual(calls,[{contextOnly:true},{kind:"E",sno:2,contextHash:"a".repeat(64)}]);assert.equal(result.updating,false);
  const none:unknown[]=[];await loadReport(async request=>{none.push(request);return fixture("E",3);});
  assert.deepEqual(none,[{contextOnly:true},{contextHash:"a".repeat(64)}]);
});
test("409 最多重做一次，第二次仍變更另讀完整 X 且清除 next",async()=>{
  for(const wins of [1,3]){
    const calls:unknown[]=[];const result=await loadReport(async request=>{calls.push(request);if(request&&"contextHash" in request)throw new ApiError("fixture",409);return fixture("E",wins);});
    assert.equal(calls.length,5);assert.equal(calls[4],undefined);assert.equal(result.updating,true);assert.equal(result.report.next_game,null);
  }
});
test("非 409 不自動重試",async()=>{
  let n=0;await assert.rejects(loadReport(async request=>{n++;if(request&&"contextHash" in request)throw new ApiError("fixture",422);return fixture();}));assert.equal(n,2);
});

const nextE2={year:2026,kind_code:"E",game_sno:2,game_date:"2026-10-10",away_team_code:B,home_team_code:L,venue:"洲際",away_starter:{acnt:null,name:null,status:"unverified",team_code:B},home_starter:{acnt:null,name:null,status:"unverified",team_code:L}};
test("Y觀戰網址固定Y身分；只有journey與第二讀同指Y才成立",()=>{
  assert.equal(previewLink(901,"C",2026),"/games/901/preview?kind=C&year=2026&tab=overview");
  const report=fixture();const journey=reportJourney(report);
  assert.equal(previewMatches({report:{...report,next_game:nextE2},journey,updating:false},"E",2),true);
  assert.equal(previewMatches({report:{...report,next_game:nextE2},journey,updating:false},"E",3),false);
  assert.equal(previewMatches({report,journey,updating:false},"E",2),false);
  assert.equal(previewMatches({report:{...report,next_game:nextE2},journey,updating:true},"E",2),false);
});
test("入口只給既存正式列；Y須定位回同一X才給觀戰網址",async()=>{
  assert.equal(nextPreviewLink({kind_code:"C",game_sno:901,year:2026}),"/playoffs?year=2026&series=C&game=901#watch");
  assert.equal(nextPreviewLink(null),null);
  assert.equal(nextPreviewLink({kind_code:"A",game_sno:1,year:2026}),null);
  const report=fixture();const journey=reportJourney(report);
  const view={report:{...report,next_game:nextE2},journey,updating:false};
  const anchor=(kind_code:ReportKind,game_sno:number):ReportAnchor=>({status:"ok",season:2026,kind_code:"E",game_sno:2,anchor:{kind_code,game_sno}});
  const asked:unknown[]=[];
  assert.equal(await nextPreviewFor(view,async(sno,kind)=>{asked.push([sno,kind]);return anchor("E",1);}),"/playoffs?year=2026&series=E&game=2#watch");
  assert.deepEqual(asked,[[2,"E"]]);
  assert.equal(await nextPreviewFor(view,async()=>anchor("E",4)),null);
  assert.equal(await nextPreviewFor(view,async()=>({status:"final",season:2026,kind_code:"E",game_sno:2})),null);
  let n=0;const announced=fixture("E",3);
  assert.equal(await nextPreviewFor({report:announced,journey:reportJourney(announced),updating:false},async()=>{n++;return anchor("E",3);}),null);
  assert.equal(n,0);
});
test("每次載入完整組裝只讀一次；查無／未完賽不重讀，第一讀回應不冒充完整回顧",async()=>{
  for(const wins of [1,3]){
    let full=0;
    const view=await loadReport(async request=>{
      const base=fixture("E",wins);
      if(request&&"contextOnly" in request)return {status:base.status,season:base.season,kind_code:base.kind_code,game_sno:base.game_sno,game:base.game,journey_context:base.journey_context};
      full++;return {...base,next_game:wins===1?nextE2:null};
    });
    assert.equal(full,1);assert.deepEqual(view.report.players,[]);assert.equal(view.updating,false);
    assert.equal(previewMatches(view,"E",2),wins===1);
  }
  let reads=0;const pending={status:"not_final",season:2026,kind_code:"E",game_sno:5} as Report;
  const view=await loadReport(async()=>{reads++;return pending;});
  assert.equal(reads,1);assert.equal(view.report,pending);assert.equal(view.journey,null);
});
