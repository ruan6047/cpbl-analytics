import assert from "node:assert/strict";
import test from "node:test";

import { gameMetadataPath } from "./entity-metadata.ts";

test("賽事 metadata 依 URL 年度與賽別查詢同一筆實體", () => {
  assert.equal(
    gameMetadataPath("1", { kind: "A", year: "2025" }),
    "/api/v1/games/1/live?kind_code=A&season=2025",
  );
  assert.equal(
    gameMetadataPath("1", { kind: "D", year: "2026" }),
    "/api/v1/games/1/live?kind_code=D&season=2026",
  );
});

test("賽事 metadata 預設一軍，拒絕不合法年度", () => {
  assert.equal(gameMetadataPath("1"), "/api/v1/games/1/live?kind_code=A");
  assert.equal(
    gameMetadataPath("1", { year: "not-a-year" }),
    "/api/v1/games/1/live?kind_code=A",
  );
});
