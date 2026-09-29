"use strict";
/**
 * Which git ref a given npm package version must install, and what happens
 * when that ref is not reachable.
 *
 * The old answer to the second question was "quietly clone the default
 * branch". That is wrong in the one case it actually fires: an npm publish
 * that lands before its git tag is pushed. Every user installing in that
 * window silently received mid-development main instead of the release they
 * asked for, with a yellow warning npm usually swallows. At one release every
 * eight days the window was small; at one a day it is a routine race.
 *
 * So there is no fallback. A pinned ref that cannot be fetched is a failed
 * install, and the message says what happened and what to do.
 */

/**
 * @param {{version?: string, testRef?: string}} opts
 * @returns {{ref: string, pinned: boolean, allowDefaultBranch: boolean, reason: string}}
 */
function resolveCloneRef(opts = {}) {
  const testRef = (opts.testRef || "").trim();
  if (testRef) {
    // This repo's own install smoke test packs the npm wrapper from a PR
    // branch and needs the runtime from that branch too. Still pinned: an
    // unreachable test ref is a broken test, not a reason to install main.
    return {
      ref: testRef,
      pinned: true,
      allowDefaultBranch: false,
      reason: "test-ref",
    };
  }

  const version = (opts.version || "").trim();
  if (version) {
    return {
      ref: `v${version}`,
      pinned: true,
      allowDefaultBranch: false,
      reason: "package-version",
    };
  }

  // package.json with no version means the published artifact is malformed.
  // Installing *something* would hide that; there is nothing safe to install.
  return {
    ref: "",
    pinned: false,
    allowDefaultBranch: false,
    reason: "no-version",
  };
}

/** Human-facing text for a pinned ref that could not be fetched. */
function unreachableRefMessage(ref, repoUrl) {
  return [
    `Release ref ${ref} is not on ${repoUrl} yet.`,
    "",
    "This install was stopped on purpose. Falling back to the default branch",
    "would have given you unreleased code under a release version number.",
    "",
    "If you just published, the git tag is probably a moment behind — retry in",
    "a minute. Otherwise install a version that is tagged:",
    `  npm install -g @artheras/aria-code@<version>`,
  ].join("\n");
}

function missingVersionMessage() {
  return [
    "This package has no version field, so there is no release to install.",
    "The published artifact is malformed — please report it.",
  ].join("\n");
}

module.exports = { resolveCloneRef, unreachableRefMessage, missingVersionMessage };
