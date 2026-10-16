import assert from "node:assert/strict";
import test from "node:test";
import { GET as report } from "../app/games/[sno]/report/route.ts";
import { GET as preview } from "../app/games/[sno]/preview/route.ts";

for (const [name, handler] of [["report", report], ["preview", preview]] as const) {
  test(`${name} 固定 307/no-store；E/C 與歷史年份的原場全保留，不呼叫 API`, async () => {
    for (const year of [2024, 2025, 2026]) for (const kind of ["E", "C"]) for (let game = 1; game <= (kind === "E" ? 4 : 7); game++) {
      const response = await handler(new Request(`https://example.test/games/${game}/${name}?year=${year}&kind=${kind}&revision=old`), { params: Promise.resolve({ sno: String(game) }) });
      assert.equal(response.status, 307);
      assert.equal(response.headers.get("cache-control"), "no-store");
      assert.equal(response.headers.get("location"), `/playoffs?year=${year}&series=${kind}&game=${game}&revision=old#watch`);
    }
  });
}
