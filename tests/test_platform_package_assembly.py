"""The step that turns built binaries into npm packages, run for real.

v0.47.0 built all five platform binaries successfully and then died in
"Assemble the platform packages", before python ran at all. Two bugs in one
six-line bash helper:

    [ -f "built/$4/$3" ] && ARGS+=(--mcp "$1=built/$4/$3")

1. `$3` is the CLI binary's name and `$4` is the MCP artifact's directory, so
   this looked for aria-code-bin inside aria-code-mcp-macos-arm64/. That never
   matches, so --mcp was never passed and the MCP binaries had been silently
   missing from every platform package.

2. A trailing `cond && ...` whose test is false makes the function return 1.
   GitHub runs `run:` under `bash --noprofile --norc -eo pipefail`, so the
   first add() call ended the step. Bug 1 guaranteed the test was always false,
   so bug 2 always fired.

Neither is visible by reading the YAML, and both are invisible to a test that
only checks the python script — which passed, having never been called. So
this extracts the step's actual script from the workflow and runs it under the
same shell flags against a fixture tree, which is the only way the interaction
of the two shows up.
"""

from __future__ import annotations

import pathlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "build-native-binaries.yml"

# What each platform's two artifacts are called, as the upload steps name them.
ARTIFACTS = {
    "darwin-arm64": ("aria-code-macos-arm64", "aria-code-bin",
                     "aria-code-mcp-macos-arm64", "aria-code-mcp-bin"),
    "darwin-x64":   ("aria-code-macos-x64", "aria-code-bin",
                     "aria-code-mcp-macos-x64", "aria-code-mcp-bin"),
    "linux-x64":    ("aria-code-linux-x64", "aria-code-bin",
                     "aria-code-mcp-linux-x64", "aria-code-mcp-bin"),
    "linux-arm64":  ("aria-code-linux-arm64", "aria-code-bin",
                     "aria-code-mcp-linux-arm64", "aria-code-mcp-bin"),
    "win32-x64":    ("aria-code-windows-x64", "aria-code-bin.exe",
                     "aria-code-mcp-windows-x64", "aria-code-mcp-bin.exe"),
}


def _assemble_script() -> str:
    doc = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    for job in doc["jobs"].values():
        for step in job.get("steps") or []:
            if step.get("name") == "Assemble the platform packages":
                return step["run"]
    raise AssertionError("no 'Assemble the platform packages' step in the workflow")


def _run(script: str, built: pathlib.Path, *, capture_args: bool = True):
    """Run the step's script under GitHub's shell flags, in a sandbox."""
    work = built.parent
    # The real step ends by invoking python; replace that call with an echo of
    # the arguments, so this tests the bash that builds them rather than
    # re-testing make_platform_packages.py (which has its own tests).
    if capture_args:
        script = script.replace(
            'python scripts/make_platform_packages.py --version "$VERSION" \\\n'
            '  --out npm/platforms "${ARGS[@]}"',
            'printf "ARG:%s\\n" "${ARGS[@]}"')
        # The folded-scalar form in YAML collapses the continuation; handle both.
        script = script.replace(
            'python scripts/make_platform_packages.py --version "$VERSION" '
            '--out npm/platforms "${ARGS[@]}"',
            'printf "ARG:%s\\n" "${ARGS[@]}"')
    out = work / "github_output"
    out.touch()
    return subprocess.run(
        ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", script],
        cwd=work, capture_output=True, text=True, timeout=60,
        env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
             "INPUT_TAG": "v9.9.9", "GITHUB_REF_NAME": "v9.9.9",
             "GITHUB_OUTPUT": str(out)},
    )


class _Fixture(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.built = self.tmp / "built"
        self.script = _assemble_script()

    def place(self, platform: str, *, cli: bool = True, mcp: bool = True) -> None:
        cli_dir, cli_file, mcp_dir, mcp_file = ARTIFACTS[platform]
        if cli:
            (self.built / cli_dir).mkdir(parents=True, exist_ok=True)
            (self.built / cli_dir / cli_file).write_bytes(b"\x7fELF")
        if mcp:
            (self.built / mcp_dir).mkdir(parents=True, exist_ok=True)
            (self.built / mcp_dir / mcp_file).write_bytes(b"\x7fELF")


class AFullSetOfArtifactsAssembles(_Fixture):
    def test_the_step_succeeds_and_passes_every_binary(self) -> None:
        for platform in ARTIFACTS:
            self.place(platform)
        proc = _run(self.script, self.built)
        self.assertEqual(proc.returncode, 0,
                         f"the step failed before python ran:\n{proc.stderr[-800:]}")
        args = [l[4:] for l in proc.stdout.splitlines() if l.startswith("ARG:")]
        for platform in ARTIFACTS:
            with self.subTest(platform=platform):
                self.assertIn(f"{platform}=built/{ARTIFACTS[platform][0]}/"
                              f"{ARTIFACTS[platform][1]}", args)

    def test_the_mcp_binaries_are_passed_too(self) -> None:
        """The regression that shipped: --mcp was never added for any platform."""
        for platform in ARTIFACTS:
            self.place(platform)
        proc = _run(self.script, self.built)
        self.assertEqual(proc.returncode, 0, proc.stderr[-800:])
        args = [l[4:] for l in proc.stdout.splitlines() if l.startswith("ARG:")]
        self.assertEqual(args.count("--mcp"), len(ARTIFACTS),
                         f"expected one --mcp per platform, got {args}")
        for platform, (_, _, mcp_dir, mcp_file) in ARTIFACTS.items():
            with self.subTest(platform=platform):
                self.assertIn(f"{platform}=built/{mcp_dir}/{mcp_file}", args)


class MissingArtifactsStopTheRelease(_Fixture):
    """Every binary pinned by the dispatcher must be available."""

    def test_a_missing_mcp_binary_fails_before_packaging(self) -> None:
        for platform in ARTIFACTS:
            self.place(platform, mcp=False)
        proc = _run(self.script, self.built)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("no MCP binary", proc.stdout)
        self.assertNotIn("ARG:", proc.stdout)

    def test_a_missing_platform_fails_before_packaging(self) -> None:
        self.place("linux-x64")
        proc = _run(self.script, self.built)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("no CLI binary for darwin-arm64", proc.stdout)
        self.assertNotIn("ARG:", proc.stdout)

    def test_no_artifacts_at_all_fails_before_packaging(self) -> None:
        self.built.mkdir(parents=True)
        proc = _run(self.script, self.built)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("no CLI binary", proc.stdout)
        self.assertNotIn("ARG:", proc.stdout)


class PlatformPackagesAreSplit(_Fixture):
    def test_cli_and_mcp_have_separate_tarball_inputs(self) -> None:
        for platform in ARTIFACTS:
            self.place(platform)
        out = self.tmp / "packages"
        args = [sys.executable, str(ROOT / "scripts" / "make_platform_packages.py"),
                "--version", "9.9.9", "--out", str(out)]
        for platform, (cli_dir, cli_file, mcp_dir, mcp_file) in ARTIFACTS.items():
            args += ["--binary", f"{platform}={self.built / cli_dir / cli_file}",
                     "--mcp", f"{platform}={self.built / mcp_dir / mcp_file}"]
        proc = subprocess.run(args, capture_output=True, text=True, timeout=20)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(len(list(out.iterdir())), 10)
        for platform in ARTIFACTS:
            for kind, name in (("", "aria-code-bin"), ("mcp-", "aria-code-mcp-bin")):
                package = out / f"aria-code-{kind}{platform}"
                manifest = json.loads((package / "package.json").read_text())
                self.assertEqual(manifest["name"], f"@artheras/aria-code-{kind}{platform}")
                self.assertEqual(manifest["version"], "9.9.9")
                binaries = list((package / "bin").iterdir())
                self.assertEqual(len(binaries), 1)
                extension = ".exe" if platform.startswith("win32") else ""
                self.assertEqual(binaries[0].name, f"{name}{extension}")


if __name__ == "__main__":
    unittest.main()
