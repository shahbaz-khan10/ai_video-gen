// Run with `npm test` (Node's built-in test runner; no extra dependencies).
import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { postFields } from "./post-fields.ts";

describe("postFields", () => {
  it("sends nothing for the defaults, so old requests are unchanged", () => {
    assert.deepEqual(postFields(undefined), {});
    assert.deepEqual(postFields({ look: "none", enhance: false }), {});
  });
  it("sends a chosen look", () => {
    assert.deepEqual(postFields({ look: "sepia", enhance: false }), { look: "sepia" });
  });
  it("sends enhance only when on", () => {
    assert.deepEqual(postFields({ look: "none", enhance: true }), { enhance: true });
    assert.deepEqual(postFields({ look: "film", enhance: true }), { look: "film", enhance: true });
  });
});
