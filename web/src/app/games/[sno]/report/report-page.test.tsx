import assert from "node:assert/strict";
import { test } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import ReportPage, { ReportPlayerDialog, ReportPlayerPeriod } from "./report-page";
import { ReportTeamStyle } from "@/components/report-team-style";
import { FieldDiagram } from "@/components/field-diagram";
import { reportJourney } from "@/lib/between-games";
import type { Report, ReportPlayer } from "@/lib/report-types";

const empty={status:"missing" as const,counts:{},sample:{},covered_game_keys:[],expected_game_keys:["2026/E/1"],coverage_status:"partial",source:"fixture",cutoff_label:"截至E1"};
const p: ReportPlayer={player_id:"fixture-p",team_code:"ADD011",role:"pitching",name:"測試投手",bats:null,throws:"右",periods:{series:empty,regular:empty,opponent_regular:empty},last_game:empty,ability:{available:false,role:"pitching"},official_pr:null,traits:null,splits:[],fielding:[],vs_starter:{status:"missing"},pitching_usage:null};
const report: Report={status:"ok",season:2026,kind_code:"E",game_sno:1,game:{year:2026,kind_code:"E",game_sno:1,game_date:"2026-10-09",home_team_code:"ACN011",away_team_code:"ADD011",home_score:1,away_score:3,venue:"洲際"},players:[p],population:[],sources:[],teams:[]};
test("正式三頁籤均保留 X 賽別年度、原賽況與可達入口",()=>{
  for(const tab of ["overview","pitchers","fielders"] as const){
    const html=renderToStaticMarkup(<ReportPage view={{report,journey:reportJourney(report),updating:false}} tab={tab}/>);
    assert.match(html,/href="\/games\/1\?kind=E&amp;year=2026"/);
    for(const target of ["overview","pitchers","fielders"]) assert.ok(html.includes(`href="/games/1/report?kind=E&amp;year=2026&amp;tab=${target}"`));
    assert.ok(html.includes('aria-current="page"'));
    assert.match(html,/統一/);assert.match(html,/中信/);
    if(tab==="pitchers"){assert.match(html,/測試投手/);assert.match(html,/aria-haspopup="dialog"/);assert.match(html,/正式登錄名單尚未核實/);}
  }
});
test("未知與未完賽頁仍可返回同一原賽況",()=>{
  for(const status of ["not_found","not_final"] as const){
    const html=renderToStaticMarkup(<ReportPage view={{report:{...report,status},journey:null,updating:false}} tab="overview"/>);
    assert.match(html,/href="\/games\/1\?kind=E&amp;year=2026"/);
  }
});
test("守位 popup 是 button，既有球員守位連結維持 anchor",()=>{
  const cells={SS:{main:"測試野手",href:"#report-player-fixture"}};
  assert.match(renderToStaticMarkup(<FieldDiagram cells={cells} onSelect={()=>{}}/>),/<button[^>]*aria-haspopup="dialog"/);
  assert.match(renderToStaticMarkup(<FieldDiagram cells={cells}/>),/href="#report-player-fixture"/);
});

test("面板投手四頁籤與野手三頁籤，左右分項保留 HR 及來源缺值",()=>{
  const pitching={...p,splits:[{item_index:"R",item_name:"對右打",plate_appearances:30,hits:7,home_runs:2,bb:1,so:9}]};
  const html=renderToStaticMarkup(<ReportPlayerDialog player={pitching} close={()=>{}} season={2026}/>);
  for(const label of ["本系列","本季例行賽","本季對該隊","逐場使用"]) assert.ok(html.includes(`>${label}</button>`));
  assert.match(html,/2 HR · 1 BB · 9 SO/);
  assert.match(html,/守位：投手/);
  assert.ok(!html.includes("關閉"));
  const batting=renderToStaticMarkup(<ReportPlayerDialog player={{...p,role:"batting",fielding:[{pos:"捕手",g:50}]}} close={()=>{}} season={2026}/>);
  assert.ok(!batting.includes("逐場使用"));
  assert.match(batting,/守位：捕手 50 場/);
});
test("面板切換的單一期間同步數字及樣本；第4期沿真用量不猜角色",()=>{
  const player={...p,periods:{series:{...empty,status:"available" as const,counts:{ip:"2.1",so:3},sample:{pa:9,outs:7}},regular:{...empty,status:"available" as const,counts:{ip:"50.0",so:60},sample:{pa:210,outs:150}},opponent_regular:{...empty,status:"available" as const,counts:{ip:"8.0",so:12},sample:{pa:35,outs:24}}},pitching_usage:{ip:"0.2",pitch_total:19,consecutive_days:1,days_to_next:null,appearances:[{game_key:"2026/E/1",date:"2026-10-09",role_type:"最後一任",outs:2,pitch_cnt:19}]}};
  for(const [period,sample,other] of [["series",9,210],["regular",210,35],["opponent_regular",35,9]] as const){
    const html=renderToStaticMarkup(<ReportPlayerPeriod player={player} period={period}/>);
    assert.ok(html.includes(`樣本 ${sample} PA`));assert.ok(!html.includes(`樣本 ${other} PA`));
  }
  const usage=renderToStaticMarkup(<ReportPlayerPeriod player={player} period="usage"/>);
  assert.match(usage,/最後一任 · 0.2 局 · 19 球/);assert.match(usage,/距下一場 — 天/);assert.ok(!usage.includes("救援"));
  assert.match(renderToStaticMarkup(<ReportPlayerPeriod player={p} period="usage"/>),/未取得可靠使用紀錄/);
});

test("球風沿站內七軸及共同 ±2 尺度，缺任一軸不畫完整比較",()=>{
  const keys=["speed","smallball","power","discipline","starter_ip","pitch_k","defense"];
  const style={team:"ADD011",axes:keys.map(key=>({key,label:key,semantics:"usable"})),seasons:[{n_teams:6,axes:Object.fromEntries(keys.map(key=>[key,{z:0.8,rank:2,raw:null}]))}]};
  const complete=renderToStaticMarkup(<ReportTeamStyle style={style}/>);
  assert.match(complete,/本季七軸球風/);assert.match(complete,/顯示截 ±2/);assert.match(complete,/第 2 \/ 6 隊/);
  const incomplete={...style,seasons:[{...style.seasons[0],axes:{...style.seasons[0].axes,power:{z:NaN,rank:2,raw:null}}}]};
  const html=renderToStaticMarkup(<ReportTeamStyle style={incomplete}/>);
  assert.match(html,/未取得完整本季球風/);assert.ok(!html.includes("本季七軸球風"));
});
