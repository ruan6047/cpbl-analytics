import assert from "node:assert/strict";
import test from "node:test";
import {confirmedFinal} from "./postseason-refresh-hint.tsx";
import type {GameStatusResponse} from "@/lib/live-game";

test("延遲提示只認同身份官方final，不用比分/異場/錯隊或中斷狀態宣告",()=>{
  const probe={year:2026,kind:"E" as const,sno:4,away:"ADD011",home:"ACN011"};
  const base={canonical_phase:"final",live_snapshot:{game_id:"2026-E-4",kind_code:"E",game_sno:4,phase:"final",source_status:"ok",away:{team:{code:"ADD011"}},home:{team:{code:"ACN011"}}}} as GameStatusResponse;
  assert.equal(confirmedFinal(base,probe),true);
  for(const change of [{game_id:"2026-C-4"},{phase:"live"},{source_status:"error"},{home:{team:{code:"AAA011"}}}])assert.equal(confirmedFinal({...base,live_snapshot:{...base.live_snapshot,...change}} as GameStatusResponse,probe),false);
  assert.equal(confirmedFinal({canonical_phase:"unknown",live_snapshot:null},probe),false);
});
