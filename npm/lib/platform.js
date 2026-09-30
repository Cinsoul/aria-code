"use strict";
/**
 * Which prebuilt binary this machine needs, and where npm put it.
 *
 * The previous install did none of this: postinstall.js ran 651 lines of
 * bootstrap on every machine — Xcode CLT, Homebrew, a Python toolchain, a git
 * clone of this repository, a venv, then pip. Every one of those is a way for
 * `npm install -g` to fail, and it made the install depend on GitHub, Homebrew
 * and PyPI all being reachable.
 *
 * Claude Code and Codex both solve it the same way, and measurably smaller:
 * a dispatcher package of 0.2 MB and 0.01 MB respectively, zero runtime
 * dependencies, and the per-platform binaries as optionalDependencies so npm
 * downloads exactly the one that matches. This module is the resolution half of
 * that, kept pure so it can be tested without a binary present.
 */

const PLATFORM_KEYS = Object.freeze([
  "darwin-arm64",
  "darwin-x64",
  "linux-x64",
  "linux-arm64",
  "win32-x64",
]);

const SCOPE = "@artheras";
const BASE = "aria-code";

/** The binary's filename inside a platform package. */
function binaryName(platform, name = "aria-code-bin") {
  return platform === "win32" ? `${name}.exe` : name;
}

/**
 * "darwin-arm64" etc. for this process, or null when unsupported.
 * @param {{platform: string, arch: string}} proc
 */
function platformKey(proc) {
  const platform = proc && proc.platform;
  const arch = proc && proc.arch;
  if (!platform || !arch) return null;
  const key = `${platform}-${arch}`;
  return PLATFORM_KEYS.includes(key) ? key : null;
}

/** The npm package that carries the binary for a platform key. */
function packageNameFor(key) {
  return `${SCOPE}/${BASE}-${key}`;
}

/** The require path of a binary inside its platform package. */
function binaryRequestFor(key, name = "aria-code-bin") {
  const platform = key.split("-")[0];
  return `${packageNameFor(key)}/bin/${binaryName(platform, name)}`;
}

/**
 * What to tell someone whose platform has no build. Never a silent fallback:
 * pip install is a real, supported path and saying so is more useful than
 * attempting a source build behind a spinner.
 */
function unsupportedMessage(proc) {
  const seen = `${(proc && proc.platform) || "?"}-${(proc && proc.arch) || "?"}`;
  return [
    `No prebuilt aria-code binary for ${seen}.`,
    "",
    "Supported by the npm install:",
    ...PLATFORM_KEYS.map((k) => `  ${k}`),
    "",
    "On any other platform install from PyPI instead, which builds for yours:",
    "  pip install aria-code",
  ].join("\n");
}

/** What to tell someone whose platform IS supported but whose package is absent. */
function missingPackageMessage(key) {
  return [
    `The aria-code binary for ${key} is not installed.`,
    "",
    `npm should have fetched ${packageNameFor(key)} as an optional dependency.`,
    "That usually means the install ran with --no-optional, or it was",
    "interrupted. Reinstalling fetches it:",
    "",
    "  npm install -g @artheras/aria-code",
    "",
    "Or install from PyPI instead:  pip install aria-code",
  ].join("\n");
}

module.exports = {
  PLATFORM_KEYS,
  SCOPE,
  BASE,
  binaryName,
  platformKey,
  packageNameFor,
  binaryRequestFor,
  unsupportedMessage,
  missingPackageMessage,
};
