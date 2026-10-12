import assert from "node:assert/strict";
import test from "node:test";
import { taipeiDate, nextTaipeiMidnight } from "./taipei-date.ts";

test("UTC12日16:10已是台北13日；日曆不跟SSR所在時區分岔",()=>{
  const now=Date.parse("2026-10-12T16:10:00Z");
  assert.equal(new Date(now).getUTCDate(),12);
  assert.equal(taipeiDate(now),"2026-10-13");
  assert.equal(nextTaipeiMidnight(now),Date.parse("2026-10-13T16:00:00Z"));
});
test("台北年界與零點前後一致",()=>{
  assert.equal(taipeiDate(Date.parse("2026-12-31T15:59:59Z")),"2026-12-31");
  assert.equal(taipeiDate(Date.parse("2026-12-31T16:00:00Z")),"2027-01-01");
});
