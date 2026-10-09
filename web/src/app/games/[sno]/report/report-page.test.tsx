import assert from "node:assert/strict";
import { test } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import ReportPage from "./report-page";
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
