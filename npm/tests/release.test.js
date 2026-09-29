"use strict";
/**
 * The install must never silently substitute unreleased code for a release.
 *
 * postinstall used to clone the default branch when the pinned tag was not on
 * the remote, behind a warning npm normally swallows. That fires in exactly
 * one situation — an npm publish that lands before its git tag — and every
 * user installing in that window got mid-development main under a release
 * version number. At one release every eight days the window was small; the
 * move to per-merge releases makes it a routine race.
 */

const assert = require("assert");
const {
  resolveCloneRef,
  unreachableRefMessage,
  missingVersionMessage,
} = require("../lib/release");

let failures = 0;
function test(name, fn) {
  try { fn(); console.log(`✓ ${name}`); }
  catch (e) { failures++; console.error(`✗ ${name}\n    ${e.message}`); }
}

test("a package version pins to its release tag", () => {
  const r = resolveCloneRef({ version: "4.4.2" });
  assert.strictEqual(r.ref, "v4.4.2");
  assert.strictEqual(r.pinned, true);
});

test("no configuration ever permits the default branch", () => {
  const cases = [
    {},
    { version: "" },
    { version: "4.4.2" },
    { testRef: "some-branch" },
    { version: "4.4.2", testRef: "some-branch" },
    { version: "   " },
    { version: undefined, testRef: undefined },
  ];
  for (const c of cases) {
    assert.strictEqual(
      resolveCloneRef(c).allowDefaultBranch, false,
      `allowDefaultBranch was true for ${JSON.stringify(c)}`
    );
  }
});

test("the CI test ref wins over the package version but stays pinned", () => {
  const r = resolveCloneRef({ version: "4.4.2", testRef: "pr-branch" });
  assert.strictEqual(r.ref, "pr-branch");
  assert.strictEqual(r.pinned, true);
  assert.strictEqual(r.reason, "test-ref");
});

test("whitespace is not a version", () => {
  const r = resolveCloneRef({ version: "  ", testRef: "  " });
  assert.strictEqual(r.ref, "");
  assert.strictEqual(r.pinned, false);
  assert.strictEqual(r.reason, "no-version");
});

test("a missing version yields no ref rather than a guess", () => {
  const r = resolveCloneRef({});
  assert.strictEqual(r.ref, "");
  assert.strictEqual(r.allowDefaultBranch, false);
});

test("the unreachable-ref message names the ref and what to do", () => {
  const m = unreachableRefMessage("v4.4.2", "https://example.com/repo.git");
  assert.ok(m.includes("v4.4.2"), "message omits the ref");
  assert.ok(m.includes("https://example.com/repo.git"), "message omits the repo");
  assert.ok(/retry/i.test(m), "message does not tell the user to retry");
  assert.ok(/on purpose/i.test(m),
    "message should say the stop was deliberate, or it reads as a bug");
});

test("the missing-version message does not suggest installing anything", () => {
  const m = missingVersionMessage();
  assert.ok(!/default branch|main/i.test(m));
});

if (failures) { console.error(`\n${failures} failing`); process.exit(1); }
console.log("\nall passing");
