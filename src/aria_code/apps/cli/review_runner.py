"""Run review_service against the configured model, interactively or headless.

    aria-code review                       # uncommitted changes, tracked and untracked
    aria-code review --base main           # everything since the merge base with main
    aria-code review --commit HEAD~1
    aria-code review --staged --json --fail-on P1     # for CI

Exit codes: 0 reviewed (nothing at or above --fail-on), 1 findings at or above
--fail-on, 2 the review could not run or the reviewer did not answer in the
expected format while --fail-on was set — a gate must not pass on a review
that did not happen.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from aria_code import review_service as rs


def make_model_call(config: dict, model: str | None = None) -> rs.ModelCall:
    """One isolated completion through the provider Aria is configured for — no tools."""
    from aria_code.apps.cli.providers.base import ConfiguredProvider, LLMDone, LLMToken

    chosen = model or config.get("review_model") or config.get("model") or ""
    if not chosen:
        raise rs.ReviewError("no model configured; set one with /model or --model")

    async def call(messages: list) -> str:
        provider = ConfiguredProvider(config, chosen)
        text = ""
        async for event in provider.stream(messages, tools=[]):
            if isinstance(event, LLMToken):
                text += event.text
            elif isinstance(event, LLMDone):
                if not event.success:
                    raise rs.ReviewError(f"{chosen}: {event.error or 'the model call failed'}")
                return event.response or text
        return text

    return call


def _load_config() -> dict:
    from aria_code.apps.cli.bootstrap import (default_config, load_aria_env, prepare_network, runtime_paths,
                                              use_macos_ca_bundle, use_system_trust_store)
    from aria_code.apps.cli.config_store import load_cli_config

    # The same environment the interactive CLI starts with: keys from ~/.aria/.env,
    # a working proxy (or none), and the system's TLS trust store.
    try:
        load_aria_env()
        prepare_network()
        if not use_system_trust_store():
            use_macos_ca_bundle()
    except Exception:
        pass
    return load_cli_config(runtime_paths(), default_config())


def run_headless(argv: list[str], *, model_call: rs.ModelCall | None = None,
                 config: dict | None = None, out=None) -> int:
    out = out or sys.stdout
    parser = argparse.ArgumentParser(prog="aria-code review", description="Review a code change.")
    scope = parser.add_mutually_exclusive_group()
    scope.add_argument("--staged", action="store_true", help="review staged changes only")
    scope.add_argument("--base", metavar="BRANCH", help="review everything since the merge base with BRANCH")
    scope.add_argument("--commit", metavar="SHA", help="review one commit")
    scope.add_argument("--file", metavar="PATH", help="review one whole file")
    parser.add_argument("--json", action="store_true", help="print the review as JSON")
    parser.add_argument("--fail-on", metavar="P0|P1|P2|P3",
                        help="exit 1 when a finding on the change is at this priority or above")
    parser.add_argument("--model", help="model to review with (default: review_model, then model)")
    parser.add_argument("--lang", choices=["en", "zh"], help="language of the review text")
    parser.add_argument("--max-chars", type=int, default=rs.DEFAULT_MAX_CHARS)
    parser.add_argument("--cwd", default=".", help="repository to review (default: current directory)")
    args = parser.parse_args(argv)

    try:
        threshold = rs.parse_priority(args.fail_on) if args.fail_on else None
    except ValueError as exc:
        parser.error(str(exc))

    target = (rs.ReviewTarget("staged") if args.staged else rs.ReviewTarget("base", args.base) if args.base
              else rs.ReviewTarget("commit", args.commit) if args.commit
              else rs.ReviewTarget("file", args.file) if args.file else rs.ReviewTarget("uncommitted"))
    try:
        inp = rs.collect(target, Path(args.cwd), max_chars=args.max_chars)
        if config is None:
            config = _load_config()
        lang = args.lang or ("zh" if str(config.get("ui_lang", "en")).lower().startswith("zh") else "en")
        call = model_call or make_model_call(config, args.model)
        result = asyncio.run(rs.run_review(inp, call, lang=lang))
    except rs.ReviewError as exc:
        print(f"aria-code review: {exc}", file=sys.stderr)
        return 2

    out.write((json.dumps(result.to_dict(), ensure_ascii=False, indent=2) if args.json
               else rs.render_text(result, lang=lang)) + "\n")
    if threshold is None:
        return 0
    if not result.structured:
        print("aria-code review: the reviewer's reply was not a structured review; failing the gate",
              file=sys.stderr)
        return 2
    worst = result.worst_priority()
    return 1 if worst is not None and worst <= threshold else 0
