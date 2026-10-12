import assert from "node:assert/strict";
import { test } from "node:test";
import { reportField, reportFieldPlayer } from "./report-field.ts";
import type { Report, ReportPlayer } from "./report-types.ts";
const base:Report={status:"ok",season:2026,kind_code:"E",game_sno:1,field_candidates:{T:{游擊手:{status:"tied",g:20,player_ids:["a","b"]}}},players:[]};
const items=["C","1B","2B","3B","SS","LF","CF","RF","DH"].map((pos,i)=>({player_id:String(i+1).padStart(10,"0"),team_code:"T",pos,order:i+1}));
test("未核實公告保持年度並列候選，缺守位不猜 DH",()=>{
  for(const status of [undefined,"unverified","announced"]){
    const report={...base,announcements:status?{lineup:{status,items}}:undefined};
    const model=reportField(report,"T");assert.equal(model.announced,false);assert.equal(model.dh,null);assert.equal(model.cells.SS?.main,"a／b");assert.equal(model.cells.SS?.href,undefined);
  }
});
test("既存中文守位逐格轉接，未知守位略過且 DH 只接受明確來源",()=>{
  const positions=["捕手","一壘手","二壘手","三壘手","游擊手","左外野手","中外野手","右外野手"];
  const report={...base,field_candidates:{T:Object.fromEntries([...positions,"未知","指定打擊"].map((pos,i)=>[pos,{status:"known",g:20,player_ids:[`p${i}`]}]))}};
  const model=reportField(report,"T");
  assert.deepEqual(Object.keys(model.cells),["C","1B","2B","3B","SS","LF","CF","RF"]);
  assert.equal(model.cells.C?.href,"#report-player-p0");
  assert.equal(model.dh?.main,"p9");assert.equal(model.announced,false);
});
test("守位投手只有投球列仍取姓名與可達面板；同人打者列優先且不跨隊",()=>{
  const pitcher={player_id:"pitch-only",team_code:"T",role:"pitching",name:"測試投手"} as ReportPlayer;
  const report={...base,players:[pitcher],field_candidates:{T:{投手:{status:"known",g:20,player_ids:[pitcher.player_id]}}}};
  const model=reportField(report,"T");
  assert.equal(model.cells.P?.main,"測試投手");
  assert.equal(model.cells.P?.href,"#report-player-pitch-only");
  assert.equal(reportFieldPlayer(report,"T",pitcher.player_id)?.role,"pitching");
  assert.equal(reportFieldPlayer(report,"other",pitcher.player_id),null);
  report.players.push({...pitcher,role:"batting"});
  assert.equal(reportFieldPlayer(report,"T",pitcher.player_id)?.role,"batting");
});
test("完整可靠公告才切換，DH 與棒次消費正式項目",()=>{
  const report={...base,announcements:{lineup:{status:"announced",items,source_version:"fixture-v",observed_at:"2026-10-10T12:00:00+08:00",pregame_evidence:{is_play_ball:"N",fetched_at:"2026-10-10T12:00:00+08:00",first_started_at:"2026-10-10T17:05:00+08:00"}}}};
  const model=reportField(report,"T");assert.equal(model.announced,true);assert.equal(model.dh?.main,"0000000009");assert.equal(model.dh?.meta,"9");assert.equal(model.cells.SS?.meta,"5");
  report.announcements.lineup.items=items.slice(0,8);assert.equal(reportField(report,"T").announced,false);
  report.announcements.lineup.items=items;
  report.announcements.lineup.pregame_evidence.first_started_at="2026-10-10T11:00:00+08:00";
  assert.equal(reportField(report,"T").announced,false);
});


test("stats同版正面SCHEDULED只切合格隊，不捏main N且未知來源保候選",()=>{
  const fetched="2026-10-12T08:00:00+08:00";
  const report:Report={...base,next_game:{year:2026,kind_code:"E",game_sno:2,game_date:"2026-10-12",away_team_code:"T",home_team_code:"U",venue:null,away_starter:{acnt:null,name:null,status:"unverified",team_code:"T"},home_starter:{acnt:null,name:null,status:"unverified",team_code:"U"}},
    announcements:{lineup:{status:"partial",items,source_type:"stats_datagame",raw_status:"SCHEDULED",source_version:"v1",observed_at:fetched,
      team_evidence:{T:{status:"announced",source_type:"stats_datagame",raw_status:"SCHEDULED",source_version:"v1",fetched_at:fetched,observed_at:fetched,first_started_at:"2026-10-12T17:05:00+08:00"},U:{status:"unverified"}}}}};
  assert.equal(reportField(report,"T").announced,true);
  assert.equal(reportField(report,"U").announced,false);
  const evidence=report.announcements!.lineup.team_evidence!.T;
  evidence.raw_status="START";assert.equal(reportField(report,"T").announced,false);
  evidence.raw_status="SCHEDULED";evidence.source_version="other";assert.equal(reportField(report,"T").announced,false);
  evidence.source_version="v1";evidence.fetched_at="2026-10-12T07:59:00+08:00";assert.equal(reportField(report,"T").announced,false);
  evidence.fetched_at=fetched;report.next_game=null;assert.equal(reportField(report,"T").announced,false);
});
