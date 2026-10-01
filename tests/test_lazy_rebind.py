"""aria_cli is imported by the route that needs it, not by every caller.

stream_ollama still borrows 12 names from aria_cli's module globals and only
resolves them after that module's import-time rebind, so an out-of-CLI caller
has to import it before taking the Ollama path. apps/channels/intake.py did that
unconditionally, which meant a channel alert analysed through Vertex — a route
that never touches stream_ollama — paid for the whole CLI anyway.

Measured on the first-alert setup path:

    cloud / configured    1539ms -> 117ms
    ollama                still imports it, at provider construction

The import is inside run_ollama rather than at runtime_bridge's module level for
the same reason it left intake: at module level the cost returns to everyone.
"""

from __future__ import annotations

import asyncio
import subprocess
import sys
import textwrap
import unittest

PRELUDE = "import sys; sys.path[:0] = ['src', 'src/aria_code', '.']\n"


def _in_subprocess(body: str) -> str:
    """Run in a fresh interpreter: sys.modules is global, so an earlier test
    importing aria_cli would make any in-process assertion vacuous."""
    proc = subprocess.run(
        [sys.executable, "-c", PRELUDE + textwrap.dedent(body)],
        capture_output=True, text=True, timeout=300,
    )
    assert proc.returncode == 0, proc.stderr[-800:]
    return proc.stdout


class TheCloudRouteDoesNotImportTheCli(unittest.TestCase):
    def test_building_a_cloud_provider_leaves_aria_cli_unimported(self):
        out = _in_subprocess("""
            from apps.cli.providers.runtime_bridge import make_provider_fn
            make_provider_fn(model='google/gemini-2.5-pro',
                             config={'local_provider': 'vertex'},
                             api_url='https://gw.example',
                             ollama_url='http://localhost:11434', tool_schemas=[])
            print('aria_cli' in sys.modules)
        """)
        self.assertEqual(out.strip(), "False",
                         "the cloud route imported the whole CLI")

    def test_importing_intake_does_not_import_the_cli(self):
        out = _in_subprocess("""
            from apps.channels import intake  # noqa: F401
            print('aria_cli' in sys.modules)
        """)
        self.assertEqual(out.strip(), "False")

    def test_intake_has_no_unconditional_cli_import(self):
        """The regression is textual: an `import aria_cli` on the default branch
        applies to every route, and nothing about a cloud turn needs it."""
        import pathlib

        source = (pathlib.Path(__file__).resolve().parents[1] / "src" / "aria_code"
                  / "apps" / "channels" / "intake.py").read_text(encoding="utf-8")
        offenders = [line.strip() for line in source.splitlines()
                     if line.strip().startswith(("import aria_cli", "from aria_cli"))]
        self.assertEqual(offenders, [], f"intake.py imports aria_cli: {offenders}")


class TheOllamaRouteStillGetsItsRebind(unittest.TestCase):
    def test_the_provider_call_imports_the_cli_and_the_borrowed_names_resolve(self):
        """Moving the import must not leave stream_ollama unbound. A closed port
        makes the call fail after the rebind, which is the part being checked."""
        out = _in_subprocess("""
            import asyncio
            from apps.cli.providers.runtime_bridge import make_provider_fn

            fn = make_provider_fn(model='qwen2.5:7b',
                                  config={'local_provider': 'ollama'},
                                  api_url=None,
                                  ollama_url='http://127.0.0.1:1',
                                  tool_schemas=[])
            print('before:', 'aria_cli' in sys.modules)

            async def main():
                try:
                    await fn('hi', [])
                except Exception:
                    pass

            asyncio.run(main())
            print('after:', 'aria_cli' in sys.modules)

            cli = sys.modules.get('aria_cli')
            globs = getattr(cli, 'stream_ollama', None)
            globs = globs.__globals__ if globs is not None else {}
            needed = ('_ACTIVE_COMMAND_POLICY', '_CONFIRM_TOOLS',
                      'execute_local_tool', '_print_tool_result', 'get_ariarc')
            print('missing:', [n for n in needed if n not in globs])
        """)
        self.assertIn("before: False", out)
        self.assertIn("after: True", out,
                      "the ollama route did not import aria_cli — stream_ollama "
                      "would run with unbound globals")
        self.assertIn("missing: []", out,
                      "stream_ollama's borrowed names did not resolve after the rebind")


if __name__ == "__main__":
    unittest.main()
