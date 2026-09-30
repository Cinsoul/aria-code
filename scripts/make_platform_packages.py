#!/usr/bin/env python3
"""Build the per-platform npm packages that carry the prebuilt binaries.

The published shape mirrors Claude Code and Codex: one dispatcher package with
zero runtime dependencies, plus one package per platform listed in its
optionalDependencies, so `npm install -g` downloads exactly the binary the
machine needs and runs no install-time code at all.

Usage:
  python scripts/make_platform_packages.py --version 4.4.3 \\
      --binary darwin-arm64=dist/macos-arm64/aria-code-bin \\
      --binary linux-x64=dist/linux-x64/aria-code-bin \\
      --mcp    darwin-arm64=dist/macos-arm64/aria-code-mcp-bin \\
      --out npm/platforms

Each --binary is <platform-key>=<path>. Keys not passed are simply not built;
the dispatcher already reports a supported-but-absent package clearly, and a
release that ships fewer platforms is better than one that ships a broken
package for a platform whose binary failed to build.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import shutil
import stat
import sys

SCOPE = "@artheras"
BASE = "aria-code"
# Kept in step with npm/lib/platform.js PLATFORM_KEYS; the test asserts it.
PLATFORM_KEYS = ("darwin-arm64", "darwin-x64", "linux-x64", "linux-arm64", "win32-x64")

# npm's own fields for refusing to install a package on the wrong machine. Worth
# setting even though the dispatcher checks too: this way npm skips the download
# rather than fetching a binary it cannot run.
OS_FOR = {"darwin": "darwin", "linux": "linux", "win32": "win32"}


def binary_name(key: str, name: str = "aria-code-bin") -> str:
    return f"{name}.exe" if key.startswith("win32") else name


def _pairs(values: list[str], flag: str) -> dict[str, pathlib.Path]:
    out: dict[str, pathlib.Path] = {}
    for raw in values or ():
        if "=" not in raw:
            raise SystemExit(f"{flag} expects <platform-key>=<path>, got {raw!r}")
        key, path = raw.split("=", 1)
        if key not in PLATFORM_KEYS:
            raise SystemExit(f"unknown platform key {key!r}; known: {', '.join(PLATFORM_KEYS)}")
        resolved = pathlib.Path(path).expanduser()
        if not resolved.is_file():
            raise SystemExit(f"{flag} {key}: no such file: {resolved}")
        out[key] = resolved
    return out


def build_one(key: str, version: str, binaries: dict[str, pathlib.Path],
              out_root: pathlib.Path) -> pathlib.Path:
    platform = key.split("-")[0]
    arch = key.split("-", 1)[1]
    pkg_dir = out_root / f"{BASE}-{key}"
    bin_dir = pkg_dir / "bin"
    if pkg_dir.exists():
        shutil.rmtree(pkg_dir)
    bin_dir.mkdir(parents=True)

    for name, source in binaries.items():
        target = bin_dir / binary_name(key, name)
        shutil.copy2(source, target)
        # npm preserves the mode it finds. A binary shipped without +x installs
        # fine and then fails with EACCES on first run.
        target.chmod(target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    (pkg_dir / "package.json").write_text(json.dumps({
        "name": f"{SCOPE}/{BASE}-{key}",
        "version": version,
        "description": f"aria-code prebuilt binary for {key}",
        "license": "Apache-2.0",
        "os": [OS_FOR[platform]],
        "cpu": [arch],
        "files": ["bin/"],
    }, indent=2) + "\n", encoding="utf-8")
    return pkg_dir


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", required=True)
    ap.add_argument("--binary", action="append", default=[],
                    help="<platform-key>=<path to aria-code-bin>")
    ap.add_argument("--mcp", action="append", default=[],
                    help="<platform-key>=<path to aria-code-mcp-bin>")
    ap.add_argument("--out", default="npm/platforms")
    args = ap.parse_args(argv[1:])

    main_bins = _pairs(args.binary, "--binary")
    mcp_bins = _pairs(args.mcp, "--mcp")
    if not main_bins:
        raise SystemExit("no --binary given; nothing to package")

    stray = set(mcp_bins) - set(main_bins)
    if stray:
        # An mcp binary with no CLI binary for the same platform would publish a
        # package the dispatcher never looks in.
        raise SystemExit(f"--mcp given for platforms with no --binary: {sorted(stray)}")

    out_root = pathlib.Path(args.out)
    out_root.mkdir(parents=True, exist_ok=True)
    built = []
    for key, path in sorted(main_bins.items()):
        binaries = {"aria-code-bin": path}
        if key in mcp_bins:
            binaries["aria-code-mcp-bin"] = mcp_bins[key]
        built.append(build_one(key, args.version, binaries, out_root))

    print(f"Built {len(built)} platform package(s) in {out_root}:")
    for pkg in built:
        names = sorted(p.name for p in (pkg / "bin").iterdir())
        print(f"  {pkg.name:34} {', '.join(names)}")
    missing = [k for k in PLATFORM_KEYS if k not in main_bins]
    if missing:
        print(f"Not built this run: {', '.join(missing)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
