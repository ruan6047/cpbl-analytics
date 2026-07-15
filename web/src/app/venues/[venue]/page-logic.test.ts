import assert from "node:assert/strict";
import test from "node:test";

import { ApiError, optionalNotFound } from "../../../lib/http-error.ts";
import { canonicalVenue, hasSplitRows } from "./page-logic.ts";

test("canonicalVenue maps every API venue alias before list lookup", () => {
  assert.equal(canonicalVenue("台中"), "國體");
  assert.equal(canonicalVenue("桃園"), "樂天桃園");
  assert.equal(canonicalVenue("亞太副場"), "亞太副");
  assert.equal(canonicalVenue("洲際"), "洲際");
});

test("optionalNotFound degrades an expected API 404 to null", async () => {
  const result = await optionalNotFound(Promise.reject(new ApiError("/venue", 404)));
  assert.equal(result, null);
});

test("optionalNotFound rethrows API source errors", async () => {
  const sourceError = new ApiError("/venue", 500);
  await assert.rejects(optionalNotFound(Promise.reject(sourceError)), (error) => error === sourceError);
});

test("optionalNotFound rethrows network errors", async () => {
  const networkError = new TypeError("fetch failed");
  await assert.rejects(optionalNotFound(Promise.reject(networkError)), (error) => error === networkError);
});

test("hasSplitRows hides a player section with no post-filter rows", () => {
  assert.equal(hasSplitRows({ top: [], bottom: [] }), false);
  assert.equal(hasSplitRows({ top: [{ player_id: "1" }], bottom: [] }), true);
  assert.equal(hasSplitRows({ top: [], bottom: [{ player_id: "2" }] }), true);
});
