import assert from "node:assert/strict";
import { test } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import ReportPage, { ReportPlayerDialog, ReportPlayerPeriod } from "./report-page";
import { ReportTeamStyle } from "@/components/report-team-style";
import { FieldDiagram } from "@/components/field-diagram";
import { previewMatches, reportJourney } from "@/lib/between-games";
import type { Report, ReportPlayer } from "@/lib/report-types";

const empty={status:"missing" as const,counts:{},sample:{},covered_game_keys:[],expected_game_keys:["2026/E/1"],coverage_status:"partial",source:"fixture",cutoff_label:"截至E1"};
const p: ReportPlayer={player_id:"fixture-p",team_code:"ADD011",role:"pitching",name:"測試投手",bats:null,throws:"右投",periods:{series:empty,regular:empty,opponent_regular:empty},last_game:empty,ability:{available:false,role:"pitching"},official_pr:null,traits:null,splits:[],fielding:[],vs_starter:{status:"missing"},pitching_usage:null};
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
  assert.doesNotMatch(html,/右投投/);
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
  const noTargetUsage=renderToStaticMarkup(<ReportPlayerPeriod player={player} period="usage" hasTarget={false}/>);
  assert.ok(!noTargetUsage.includes("距下一場"));assert.match(noTargetUsage,/合計 0.2 局 · 19 球/);
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

test("中央系列總勝數跟客主隊卡同序，不沿公告 a/b 順序",()=>{
  const twoGames={...report,game_sno:2,game:{...report.game!,game_sno:2,game_date:"2026-10-10"},journey_context:{
    summary:[{kind_code:"E",team1_code:"ADD011",team2_code:"ACN011",games:[
      {game_no:1,game_sno:1,date:"2026-10-09",home_code:"ACN011",home_score:5,away_code:"ADD011",away_score:3},
      {game_no:2,game_sno:2,date:"2026-10-10",home_code:"ADD011",home_score:1,away_code:"ACN011",away_score:0},
    ]}],rows:[],sources:[],context_hash:"fixture-order",cutoff_date:"2026-10-10",through_game_keys:["2026/E/1","2026/E/2"],order_consistent:true,
  }};
  for(const [away,home,expected] of [["ACN011","ADD011","2 : 1"],["ADD011","ACN011","1 : 2"]] as const){
    const anchored={...twoGames,game:{...twoGames.game,away_team_code:away,home_team_code:home}};
    const journey=reportJourney(anchored);
    assert.ok(journey);
    assert.equal(journey.series.E.tally.a.code,"ADD011");
    assert.equal(journey.series.E.tally.b.code,"ACN011");
    assert.equal(journey.series.E.tally.a.total,1);
    assert.equal(journey.series.E.tally.b.total,2);
    const html=renderToStaticMarkup(<ReportPage view={{report:anchored,journey,updating:false}} tab="overview"/>);
    assert.ok(html.includes(`>${expected}</p>`),`中央總勝數應為客隊 ${away}：主隊 ${home} = ${expected}`);
    assert.match(html,/實際 1 勝＋規則 1 勝/);
    assert.match(html,/還差 1 勝/);
    assert.match(html,/還差 2 勝/);
  }
});

test("Y已完賽回看仍固定X/Y，三頁籤明示開賽前背景",()=>{
  const historical: Report={...report,game_sno:2,game:{...report.game!,game_sno:2,game_date:"2026-10-10",away_team_code:"ACN011",home_team_code:"ADD011",away_score:0,home_score:1},
    journey_context:{summary:[{kind_code:"E",team1_code:"ADD011",team2_code:"ACN011",games:[
      {game_no:1,game_sno:1,date:"2026-10-09",home_code:"ACN011",home_score:5,away_code:"ADD011",away_score:3},
      {game_no:2,game_sno:2,date:"2026-10-10",home_code:"ADD011",home_score:1,away_code:"ACN011",away_score:0},
    ]}],rows:[{year:2026,kind_code:"E",game_sno:3,game_date:"2026-10-11",away_team_code:"ADD011",home_team_code:"ACN011",away_score:4,home_score:2,completed:true,venue:"洲際"}],sources:[],context_hash:"a".repeat(64),cutoff_date:"2026-10-10",through_game_keys:["2026/E/1","2026/E/2"],order_consistent:true},
    watch_points:[{team_code:"ADD011",player_id:p.player_id,origin:"last_game",count_line:{outs:18},question:"下一場能否延續這段表現？"}]};
  const journey=reportJourney(historical);
  assert.equal(journey?.next?.row?.game_sno,3);
  assert.equal(journey?.next?.score,null);
  for(const tab of ["overview","pitchers","fielders"] as const){
    const html=renderToStaticMarkup(<ReportPage view={{report:historical,journey,updating:false}} tab={tab}/>);
    assert.match(html,/<header>[\s\S]*?開賽前背景[\s\S]*?<\/header>/);
    assert.match(html,/2026-10-10 完賽後/);
    assert.doesNotMatch(html,/終場 0 : 1/);
    assert.match(html,/href="\/games\/2\?kind=E&amp;year=2026"/);
    if(tab==="overview"){
      assert.match(html,/開賽前背景：統一獅對中信兄弟/);
      assert.match(html,/該場觀察重點/);
      assert.doesNotMatch(html,/能否延續這段表現/);
      assert.match(html,/局數 6.0/);
      assert.ok(html.includes('>2 : 1</p>'));
    }
  }
});
test("沒有Y或系列終結不造開賽前背景、先發或未來式觀察題",()=>{
  const noTarget={...report,watch_points:[{team_code:p.team_code,player_id:p.player_id,origin:"last_game" as const,count_line:{outs:18},question:"下一場能否延續這段表現？"}]};
  const finished: Report={...noTarget,kind_code:"C",game_sno:4,game:{...report.game!,kind_code:"C",game_sno:4,game_date:"2026-10-21",away_team_code:"ADD011",home_team_code:"AAA011",away_score:0,home_score:5},journey_context:{
    summary:[{kind_code:"E",team1_code:"ADD011",team2_code:"ACN011",games:Array.from({length:3},(_,i)=>({game_no:i+1,game_sno:i+1,date:`2026-10-${9+i}`,home_code:"ACN011",home_score:1,away_code:"ADD011",away_score:3}))},
      {kind_code:"C",team1_code:"ADD011",team2_code:"AAA011",games:Array.from({length:4},(_,i)=>({game_no:i+1,game_sno:i+1,date:`2026-10-${17+i}`,home_code:"AAA011",home_score:5,away_code:"ADD011",away_score:0}))}],
    rows:[],sources:[],context_hash:"b".repeat(64),cutoff_date:"2026-10-21",through_game_keys:["2026/C/1","2026/C/2","2026/C/3","2026/C/4"],order_consistent:true}};
  const ended=reportJourney(finished);
  assert.equal(ended?.series.C.tally.decided,true);
  assert.equal(ended?.next,null);
  for(const [data,journey] of [[noTarget,null],[finished,ended]] as const) for(const tab of ["overview","pitchers","fielders"] as const){
    const html=renderToStaticMarkup(<ReportPage view={{report:data,journey,updating:false}} tab={tab}/>);
    assert.ok(!html.includes("開賽前背景"));
    assert.ok(!html.includes("下一場能否"));
    assert.ok(!html.includes("下一場先發"));
    assert.ok(!html.includes("該場公告先發"));
    assert.ok(!html.includes("距下一場"));
    assert.ok(!html.includes("查看下一場賽況"));
    assert.ok(!html.includes("查看該場賽況"));
    if(tab==="overview") { assert.match(html,/局數 6.0/); assert.doesNotMatch(html,/outs 18/); }
  }
});


test("有Y的野手面板保留可靠ID配對；無Y不將既有配對當公告先發",()=>{
  const base: ReportPlayer={...p,role:"batting",periods:{series:{...empty,status:"available",counts:{pa:11,h:4},sample:{pa:11,ab:9}},regular:empty,opponent_regular:empty}};
  for(const vs_starter of [
    {status:"available",pitcher_id:"0000007778",counts:{pa:23,h:8},sample:{pa:23,ab:20},updated_at:"2026-10-10T02:00:00Z"},
    {status:"missing",pitcher_id:"0000007778"},
  ] as ReportPlayer["vs_starter"][]){
    const player={...base,vs_starter};
    const withTarget=renderToStaticMarkup(<ReportPlayerDialog player={player} close={()=>{}} season={2026} hasTarget={true}/>);
    assert.match(withTarget,/本季對該場公告先發/);
    if(vs_starter.counts) assert.match(withTarget,/23 PA · 20 AB/);
    else assert.match(withTarget,/本站未取得投打配對/);
    const noTarget=renderToStaticMarkup(<ReportPlayerDialog player={player} close={()=>{}} season={2026} hasTarget={false}/>);
    assert.ok(!noTarget.includes("本季對該場公告先發"));
    assert.ok(!noTarget.includes("23 PA · 20 AB"));
    assert.ok(!noTarget.includes("本站未取得投打配對"));
    for(const label of ["本系列","本季例行賽","本季對該隊"]) assert.ok(noTarget.includes(`>${label}</button>`));
    assert.match(noTarget,/樣本 11 PA/);
    assert.match(noTarget,/能力、官方 PR 與特性固定 2026 年一軍例行賽/);
    assert.match(noTarget,/href="\/players\/fixture-p\?year=2026"/);
  }
});


test("能力特色保留大雷達與逐軸PR，期間列完整指標但不補零", () => {
  const player: ReportPlayer = {...p, ability:{available:true, role:"pitching",signature:"三振",axes:[{key:"k",label:"三振",pr:88,grade:"A",components:[]},{key:"bb",label:"控球",pr:67,grade:"B",components:[]}],overall:{pr:77,grade:"B"}}, periods:{...p.periods,series:{...empty,status:"available",counts:{ip:"6.0",so:9,bb:1,h:3,hr:0,era:1.5,whip:0.67,pitch_cnt:89},sample:{pa:23,outs:18}}}};
  const html = renderToStaticMarkup(<ReportPlayerDialog player={player} close={()=>{}} season={2026}/>);
  assert.match(html,/能力特色/);
  assert.match(html,/三振型/);
  assert.match(html,/PR 88/);
  for (const label of ["ERA", "WHIP", "安打", "全壘打", "球數"]) assert.ok(html.includes(label));
  assert.doesNotMatch(html,/>關閉<|aria-label="關閉/);
});

test("可信公告先發獨立能力卡，其他投手仍以個人卡進面板，不把未核先發補人", () => {
  const starter = {...p, ability:{available:true, role:"pitching" as const,axes:[{key:"k",label:"三振",pr:80,grade:"A",components:[]}]}};
  const data: Report = {...report,players:[starter,{...p,player_id:"reliever",name:"後援甲"}],next_game:{year:2026,kind_code:"E",game_sno:2,game_date:"2026-10-10",away_team_code:"ADD011",home_team_code:"ACN011",venue:"洲際",away_starter:{acnt:p.player_id,name:p.name,status:"announced",team_code:"ADD011"},home_starter:{acnt:null,name:null,status:"unverified",team_code:"ACN011"}}};
  data.journey_context = {summary:[{kind_code:"E",team1_code:"ADD011",team2_code:"ACN011",games:[{game_no:1,game_sno:1,date:"2026-10-09",away_code:"ADD011",away_score:3,home_code:"ACN011",home_score:1}]}],rows:[],sources:[],context_hash:"fixture-starter",cutoff_date:"2026-10-09",through_game_keys:["2026/E/1"],order_consistent:true};
  const journey = reportJourney(data);
  assert.ok(journey?.next, "有正式 X 截止集合才有 Y，不能僅由 next_game 假造");
  const html = renderToStaticMarkup(<ReportPage view={{report:data,journey,updating:false}} tab="pitchers"/>);
  assert.match(html,/該場公告先發/);
  assert.match(html,/本季能力雷達圖/);
  assert.match(html,/PR 80/);
  assert.match(html,/其他投手 · 含後援/);
  assert.match(html,/後援甲/);
  assert.match(html,/本站尚未取得可靠先發公告/);
});

test("觀察重點保留長打正證，與全壘打分開呈現且不露原始欄位", () => {
  const hitter: ReportPlayer = {...p,role:"batting",name:"長打選手",last_game:{...empty,status:"available",counts:{pa:4,h:2,hr:1,xbh:2,rbi:0},sample:{pa:4}}};
  const data: Report = {...report,players:[hitter],watch_points:[{team_code:hitter.team_code,player_id:hitter.player_id,origin:"last_game",count_line:{pa:4,h:2,hr:1,xbh:2,bb:0},question:"下一場能否延續這段表現？"}]};
  const html = renderToStaticMarkup(<ReportPage view={{report:data,journey:null,updating:false}} tab="overview"/>);
  assert.match(html,/長打 2/);
  assert.match(html,/全壘打 1/);
  assert.doesNotMatch(html,/xbh|outs|能否延續/);
});

test("跨系列比較三頁用兄弟/味全，X回顧與返回連結保持E4，不假造C1完賽", () => {
  const target = {year:2026,kind_code:"C",game_sno:901,game_date:"2026-10-17",away_team_code:"ACN011",home_team_code:"AAA011",venue:"大巨蛋",away_starter:{acnt:null,name:null,status:"unverified",team_code:"ACN011"},home_starter:{acnt:null,name:null,status:"unverified",team_code:"AAA011"}};
  const comparePitcher = {...p,team_code:"AAA011",name:"味全合成投手"};
  const data: Report = {...report,game_sno:4,game:{...report.game!,game_sno:4},comparison:{game:target,kind_code:"C",series_game_keys:[],usage_cutoff_label:"近期使用，截至2026/E/4完賽",players:[comparePitcher],population:[],teams:[],watch_points:[],field_candidates:{},announcements:{lineup:{status:"unverified",items:[]}},coverage:{games:0,with_pitching:0,with_batting:0}}};
  for (const tab of ["overview","pitchers","fielders"] as const) {
    const html = renderToStaticMarkup(<ReportPage view={{report:data,journey:null,updating:false}} tab={tab}/>);
    assert.match(html,/<h1[^>]*>中信兄弟對味全龍/);
    assert.match(html,/統一獅對中信兄弟.*回顧/);
    assert.match(html,/href="\/games\/4\?kind=E&amp;year=2026"/);
    assert.match(html,/台灣大賽本系列尚無完賽資料/);
    assert.doesNotMatch(html,/C.*901.*完賽/);
    if (tab==="pitchers") assert.match(html,/味全合成投手/);
  }
});

test("C比較的E近期先發紀錄不能標成C本系列曾先發", () => {
  const target = {year:2026,kind_code:"C",game_sno:901,game_date:"2026-10-17",away_team_code:"ACN011",home_team_code:"AAA011",venue:"大巨蛋",away_starter:{acnt:null,name:null,status:"unverified",team_code:"ACN011"},home_starter:{acnt:null,name:null,status:"unverified",team_code:"AAA011"}};
  const recentPitcher: ReportPlayer = {...p,team_code:"ACN011",pitching_usage:{started:true,through_game_keys:["2026/E/4"],cutoff_label:"截至2026/E/4完賽",appearances:[{game_key:"2026/E/4",date:"2026-10-12",role_type:"先發",outs:18,pitch_cnt:90}]}};
  const data: Report = {...report,game_sno:4,comparison:{game:target,kind_code:"C",series_game_keys:[],usage_cutoff_label:"近期使用，截至2026/E/4完賽",players:[recentPitcher],population:[],teams:[],watch_points:[],field_candidates:{},announcements:{lineup:{status:"unverified",items:[]}},coverage:{games:0,with_pitching:0,with_batting:0}}};
  const html = renderToStaticMarkup(<ReportPage view={{report:data,journey:null,updating:false}} tab="pitchers"/>);
  assert.match(html,/台灣大賽本系列尚無完賽資料/);
  assert.match(html,/近期曾先發/);
  assert.doesNotMatch(html,/系列曾先發/);
  assert.match(renderToStaticMarkup(<ReportPlayerPeriod player={recentPitcher} period="usage"/>),/截至2026\/E\/4完賽/);
});

test("X回顧只在傳入可靠Y時以「下一場觀戰報告」連Y；Y觀戰頁頁籤固定Y身分、另連截至場",()=>{
  const next={year:2026,kind_code:"E",game_sno:2,game_date:"2026-10-10",away_team_code:"ACN011",home_team_code:"ADD011",venue:"洲際",away_starter:{acnt:null,name:null,status:"unverified",team_code:"ACN011"},home_starter:{acnt:null,name:null,status:"unverified",team_code:"ADD011"}};
  const data: Report={...report,next_game:next,
    journey_context:{summary:[{kind_code:"E",team1_code:"ADD011",team2_code:"ACN011",games:[{game_no:1,game_sno:1,date:"2026-10-09",away_code:"ADD011",away_score:3,home_code:"ACN011",home_score:1}]}],
      rows:[{year:2026,kind_code:"E",game_sno:2,game_date:"2026-10-10",away_team_code:"ACN011",home_team_code:"ADD011",away_score:0,home_score:0,completed:false,venue:"洲際"}],sources:[],context_hash:"a".repeat(64),cutoff_date:"2026-10-09",through_game_keys:["2026/E/1"],order_consistent:true}};
  const journey=reportJourney(data);
  assert.equal(journey?.next?.row?.game_sno,2);
  const href="/games/2/preview?kind=E&year=2026&tab=overview";
  const withTarget=renderToStaticMarkup(<ReportPage view={{report:data,journey,updating:false}} tab="overview" nextPreview={href}/>);
  assert.ok(withTarget.includes('href="/games/2/preview?kind=E&amp;year=2026&amp;tab=overview"'));
  assert.match(withTarget,/>下一場觀戰報告<\/a>/);
  const noTarget=renderToStaticMarkup(<ReportPage view={{report:data,journey,updating:false}} tab="overview"/>);
  assert.ok(!noTarget.includes("/preview?"));assert.ok(!noTarget.includes("下一場觀戰報告"));
  for(const tab of ["overview","pitchers","fielders"] as const){
    const html=renderToStaticMarkup(<ReportPage view={{report:data,journey,updating:false}} tab={tab} preview={{kind:"E",sno:2}} nextPreview={href}/>);
    assert.match(html,/<h1[^>]*>中信兄弟對統一獅 · 下一場觀戰報告<\/h1>/);
    for(const target of ["overview","pitchers","fielders"]) assert.ok(html.includes(`href="/games/2/preview?kind=E&amp;year=2026&amp;tab=${target}"`));
    assert.ok(!html.includes('href="/games/1/report?kind=E&amp;year=2026&amp;tab=pitchers"'));
    assert.ok(html.includes('href="/games/1/report?kind=E&amp;year=2026&amp;tab=overview"'));
    assert.match(html,/截至場場間報告/);
    assert.ok(!html.includes(">下一場觀戰報告</a>"));
  }
});

test("同系列換主場時，Y觀戰頁卡片、中央勝場與投野手左右沿Y；X頁仍沿X",()=>{
  const next={year:2026,kind_code:"E",game_sno:2,game_date:"2026-10-10",away_team_code:"ACN011",home_team_code:"ADD011",venue:"洲際",away_starter:{acnt:null,name:null,status:"unverified",team_code:"ACN011"},home_starter:{acnt:null,name:null,status:"unverified",team_code:"ADD011"}};
  const data: Report={...report,game:{...report.game!,away_score:1,home_score:5},next_game:next,
    journey_context:{summary:[{kind_code:"E",team1_code:"ADD011",team2_code:"ACN011",games:[{game_no:1,game_sno:1,date:"2026-10-09",away_code:"ADD011",away_score:1,home_code:"ACN011",home_score:5}]}],
      rows:[{year:2026,kind_code:"E",game_sno:2,game_date:"2026-10-10",away_team_code:"ACN011",home_team_code:"ADD011",away_score:0,home_score:0,completed:false,venue:"洲際"}],sources:[],context_hash:"c".repeat(64),cutoff_date:"2026-10-09",through_game_keys:["2026/E/1"],order_consistent:true}};
  assert.equal(data.comparison,undefined);
  const journey=reportJourney(data);
  assert.equal(journey?.next?.row?.game_sno,2);
  const view={report:data,journey,updating:false};
  assert.equal(previewMatches(view,"E",2),true);
  const cards=(html:string)=>[...html.matchAll(/>(客隊|主隊)<\/p>[\s\S]*?(中信兄弟|統一獅)[\s\S]*?(還差 \d 勝)/g)].map(m=>m.slice(1).join(" "));
  const columns=(html:string)=>[...html.matchAll(/aria-label="(中信兄弟|統一獅)統計期間"/g)].map(m=>m[1]);
  for(const tab of ["overview","pitchers","fielders"] as const){
    const html=renderToStaticMarkup(<ReportPage view={view} tab={tab} preview={{kind:"E",sno:2}}/>);
    assert.match(html,/<h1[^>]*>中信兄弟對統一獅 · 下一場觀戰報告<\/h1>/);
    assert.match(html,/href="\/games\/1\?kind=E&amp;year=2026"/);
    assert.ok(html.includes('href="/games/1/report?kind=E&amp;year=2026&amp;tab=overview"'));
    assert.match(html,/2026-10-09 完賽後/);
    if(tab==="overview"){
      assert.deepEqual(cards(html),["客隊 中信兄弟 還差 1 勝","主隊 統一獅 還差 3 勝"]);
      assert.ok(html.includes(">2 : 0</p>"),"中央勝場應為Y客隊兄弟：主隊統一");
    } else assert.deepEqual(columns(html),["中信兄弟","統一獅"]);
  }
  for(const tab of ["overview","pitchers","fielders"] as const){
    const html=renderToStaticMarkup(<ReportPage view={view} tab={tab}/>);
    assert.match(html,/<h1[^>]*>統一獅對中信兄弟 · 場間報告<\/h1>/);
    assert.match(html,/href="\/games\/1\?kind=E&amp;year=2026"/);
    assert.match(html,/2026-10-09 完賽後/);
    if(tab==="overview"){
      assert.deepEqual(cards(html),["客隊 統一獅 還差 3 勝","主隊 中信兄弟 還差 1 勝"]);
      assert.ok(html.includes(">0 : 2</p>"));
    } else assert.deepEqual(columns(html),["統一獅","中信兄弟"]);
  }
});

test("#273 N02／N06／N08：系列未開打預設本季例行賽、野手頁不列純投手、頁尾時戳與來源名給一般讀者", () => {
  const target = {year:2026,kind_code:"C",game_sno:1,game_date:"2026-10-17",away_team_code:"ACN011",home_team_code:"AAA011",venue:"大巨蛋",away_starter:{acnt:null,name:null,status:"unverified",team_code:"ACN011"},home_starter:{acnt:null,name:null,status:"unverified",team_code:"AAA011"}};
  const fielder: ReportPlayer = {...p,player_id:"f1",team_code:"ACN011",role:"batting",name:"野手甲",fielding:[{pos:"游擊手",g:80}]};
  const pitcherBatting: ReportPlayer = {...p,player_id:"p1",team_code:"ACN011",role:"batting",name:"投手打擊",fielding:[{pos:"投手",g:50}]};
  const data: Report = {...report,game_sno:4,read_at:"2026-10-14T04:49:44.916317+00:00",regular_coverage:{year:2026,kind:"A",closed_before_X:true,covered_game_keys:[]},
    sources:[{source:"livelog",source_version:null,reference:"/api/x",updated_at:"2026-10-13T02:10:12.653764+00:00",coverage_status:"available"},{source:"livelog",source_version:null,reference:"/api/y",fetched_at:null,coverage_status:"verified"},{source:"mystery_table",source_version:null,reference:"/api/z"}],
    comparison:{game:target,kind_code:"C",series_game_keys:[],usage_cutoff_label:"近期使用，截至2026/E/4完賽",players:[fielder,pitcherBatting],population:[],teams:[],watch_points:[],field_candidates:{},announcements:{lineup:{status:"unverified",items:[]}},coverage:{games:0,with_pitching:0,with_batting:0}}};
  const html = renderToStaticMarkup(<ReportPage view={{report:data,journey:null,updating:false}} tab="fielders"/>);
  assert.match(html,/台灣大賽還沒開打，下列先顯示本季例行賽/);
  assert.match(html,/aria-pressed="true"[^>]*>本季例行賽</);
  assert.match(html,/野手甲/);
  assert.doesNotMatch(html,/投手打擊/);
  assert.match(html,/本頁資料讀取於 2026-10-14 12:49（台北）/);
  assert.doesNotMatch(html,/\+00:00|\.916317|>livelog<|closed_before_X/);
  assert.match(html,/逐打席紀錄：2 筆，最近更新 2026-10-13 10:10（台北）/);
  assert.match(html,/其他來源（mystery_table）/);
  assert.match(html,/逐筆來源連結（3 筆）/);
  // 系列已有完賽場時維持「本系列」預設。
  const started = renderToStaticMarkup(<ReportPage view={{report:{...data,comparison:{...data.comparison!,series_game_keys:["2026/C/1"]}},journey:null,updating:false}} tab="fielders"/>);
  assert.match(started,/aria-pressed="true"[^>]*>本系列</);
  assert.doesNotMatch(started,/下列先顯示本季例行賽/);
});
