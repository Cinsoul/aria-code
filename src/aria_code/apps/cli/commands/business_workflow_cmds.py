"""BusinessWorkflowCommandsMixin — research, earnings, realty, ops workflow commands."""

from __future__ import annotations

from aria_code.apps.cli.i18n import ui_text

from ._business_render import p, print_realty_result, print_risk_scan


import json
import asyncio
import datetime
import time
import shlex
from typing import Dict, Any, Optional


import json
import asyncio
import datetime
import time
import shlex
import sys
import os
from typing import Dict, Any, Optional


import json
import asyncio
import datetime
import time
import shlex
import sys
import os
from typing import Dict, Any, Optional


class BusinessWorkflowCommandsMixin:
    """Mixin: financial research and realty/operations workflow commands."""

    async def cmd_research(self, args: str):
        sym = args.strip().upper() or "AAPL"
        # Route research through the deterministic team workflow so data
        # fetching, rendering, and artifact saving happen in one service path.
        await self.cmd_team(f"{sym} --full")

    async def cmd_earnings_workflow(self, args: str):
        """/earnings SYMBOL — the earnings themselves; --report writes the Markdown report."""
        parts = args.strip().split()
        sym = next((t.upper() for t in parts if not t.startswith("--")), "AAPL")
        if "--report" in parts:
            period = " ".join(t for t in parts[1:] if not t.startswith("--")) or "最近一个季度"
            report_type = "deep" if any(k in period.lower() for k in ("deep", "深度", "全年", "年报", "10-k")) else "standard"
            await self.cmd_report(f"{sym} --format md --type {report_type}")
            return
        from aria_code.apps.cli.earnings_view import fetch_earnings, render_earnings

        lang = "zh" if str(self.terminal.config.get("ui_lang", "en")).lower().startswith("zh") else "en"
        status = ui_text(self, f"获取 {sym} 财报数据", f"Fetching {sym} earnings")
        if self.context.has_rich:
            with self.context.console.status(f"[dim]{status}…[/dim]", spinner="dots"):
                data = await asyncio.get_event_loop().run_in_executor(None, fetch_earnings, sym)
        else:
            data = await asyncio.get_event_loop().run_in_executor(None, fetch_earnings, sym)
        if not data.get("success"):
            from ._ui import print_error
            print_error(self.context, data.get("error", "No earnings data"),
                        ui_text(self, f"可以试试 /report {sym}", f"Try /report {sym} instead"))
            return
        if self.context.has_rich:
            render_earnings(data, self.context.console, lang)
        else:
            for row in data.get("history", []):
                print(f"  {row['date']}  est {row.get('estimate')}  actual {row['reported']}  "
                      f"surprise {row.get('surprise_pct')}")

    async def cmd_asset_diag(self, args: str):
        asset_id = args.strip()
        if not asset_id:
            p(self.context, "用法: /asset-diag <资产ID或名称>  例: /asset-diag asset_000001", "dim")
            return
        asset_info = {}
        api_url = self.terminal.config.get("api_url", "http://localhost:8000")
        try:
            import aiohttp
            async with aiohttp.ClientSession(trust_env=True) as sess:
                async with sess.get(
                    f"{api_url}/api/realty/assets/{asset_id}",
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as resp:
                    if resp.status == 200:
                        body = await resp.json()
                        raw = body.get("data", {})
                        asset_info = {
                            "area": raw.get("area_sqm", 0),
                            "location": raw.get("address", asset_id),
                            "vacancy_days": raw.get("vacancy_days", 0),
                            "expected_rent": raw.get("monthly_rent_market", 0),
                            "allowed_business": raw.get("allowed_business_types", []),
                            "property_state": raw.get("property_state", "正常"),
                            "floor_height": raw.get("floor_height", 0),
                        }
                        p(self.context, f"已从 API 加载资产: {raw.get('name', asset_id)}", "ok")
        except Exception:
            pass
        if not asset_info:
            self._realty_needs(asset_id, "Usage: /asset-diag <asset_id>")
            return
        await self._run_realty_agent("asset_diagnosis", asset_id, {"asset_info": asset_info})

    async def cmd_contract_draft(self, args: str):
        parts = args.split() if args else []
        project_id = parts[0] if parts and not parts[0].startswith("--") else ""
        nego = {"guaranteed_amount": 0, "revenue_share_pct": 0}
        for i, p in enumerate(parts):
            if p == "--guaranteed" and i + 1 < len(parts):
                try:
                    nego["guaranteed_amount"] = float(parts[i + 1])
                except ValueError:
                    pass
            elif p == "--share" and i + 1 < len(parts):
                try:
                    nego["revenue_share_pct"] = float(parts[i + 1])
                except ValueError:
                    pass
        if not project_id or not (nego["guaranteed_amount"] or nego["revenue_share_pct"]):
            from ._ui import print_error
            print_error(self.context,
                        ui_text(self, "起草合同需要项目 ID 和至少一项条款。", "A draft needs a project ID and at least one term."),
                        "Usage: /contract-draft <project_id> --guaranteed 30000 --share 10")
            return
        await self._run_realty_agent("contract_rules", project_id, {
            "negotiation": nego,
            "asset_info": {"name": project_id},
            "operator_info": {},
        })

    async def cmd_revenue_calc(self, args: str):
        parts = args.split() if args else []
        if len(parts) < 2:
            p(self.context, "用法: /revenue-calc <project_id> <总流水> [退款]  例: /revenue-calc proj_001 200000", "dim")
            return
        project_id = parts[0]
        try:
            gross = float(parts[1])
            refunds = float(parts[2]) if len(parts) > 2 else 0.0
        except ValueError:
            p(self.context, "流水金额必须为数字", "error")
            return
        api_url = self.terminal.config.get("api_url", "http://localhost:8000")
        rules = {}
        try:
            import aiohttp
            async with aiohttp.ClientSession(trust_env=True) as sess:
                async with sess.get(f"{api_url}/api/realty/contracts/{project_id}",
                                    timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status == 200:
                        body = await resp.json()
                        rules = body.get("data", {})
        except Exception:
            pass
        if not rules:
            self._realty_needs(project_id, "Usage: /revenue-calc <project_id> <gross> [refunds]")
            return
        await self._run_realty_agent("revenue_share", project_id, {
            "contract_rules": rules,
            "transaction_data": {"gross_revenue": gross, "refunds": refunds},
        })

    async def cmd_realty_risk_scan(self, args: str):
        project_id = args.strip()
        if not project_id:
            self._realty_needs(None, "Usage: /risk-scan <project_id>")
            return
        if self.context.has_rich:
            self.context.console.print(f"\n  [bold]{ui_text(self, '风险扫描', 'Risk scan')}[/bold]  "
                                       f"{ui_text(self, '项目', 'project')}: [cyan]{project_id}[/cyan]")
        api_url = self.terminal.config.get("api_url", "http://localhost:8000")
        try:
            import aiohttp
            async with aiohttp.ClientSession(trust_env=True) as sess:
                async with sess.get(
                    f"{api_url}/api/realty/risks/scan/{project_id}",
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        print_risk_scan(self.context, data)
                        return
        except Exception:
            pass
        # Running the team on {} produced findings about a project it knew
        # nothing of.
        self._realty_needs(project_id, "Usage: /risk-scan <project_id>")

    async def cmd_ops_report(self, args: str):
        project_id = args.strip()
        if not project_id:
            self._realty_needs(None, "Usage: /ops-report <project_id>")
            return
        api_url = self.terminal.config.get("api_url", "http://localhost:8000")
        project_info = {"name": project_id, "area": 0, "business_type": "未知"}
        performance_data = {}
        marketing_data = {}
        try:
            import aiohttp
            async with aiohttp.ClientSession(trust_env=True) as sess:
                async with sess.get(
                    f"{api_url}/api/realty/assets/{project_id}",
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as resp:
                    if resp.status == 200:
                        raw = (await resp.json()).get("data", {})
                        project_info = {
                            "name": raw.get("name", project_id),
                            "area": raw.get("area_sqm", 0),
                            "business_type": raw.get("current_business_type", "未知"),
                            "open_date": raw.get("open_date", ""),
                        }
                async with sess.get(
                    f"{api_url}/api/realty/revenue/splits?project_id={project_id}&page_size=3",
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as resp2:
                    if resp2.status == 200:
                        splits = (await resp2.json()).get("data", {}).get("splits", [])
                        if splits:
                            revenues = [s["split_result"].get("gross_revenue", 0) for s in splits]
                            avg_rev = sum(revenues) / len(revenues)
                            performance_data = {"monthly_revenue": avg_rev, "daily_visits": 0}
                            p(self.context, f"已加载近 {len(splits)} 期分账数据，月均流水 {avg_rev:,.0f}元", "ok")
        except Exception:
            pass
        if not performance_data:
            self._realty_needs(project_id, "Usage: /ops-report <project_id>")
            return
        await self._run_realty_agent("ops_optimize", project_id, {
            "project_info": project_info,
            "performance_data": performance_data,
            "marketing_data": marketing_data,
            "peer_benchmarks": {"revenue_per_sqm": 300},
        })

    async def cmd_exit_calc(self, args: str):
        parts = args.split() if args else []
        project_id = parts[0] if parts and not parts[0].startswith("--") else ""
        if not project_id:
            self._realty_needs(None, "Usage: /exit-calc <project_id> [--reason …]")
            return
        contract_loaded = False
        reason = "到期终止"
        for i, p in enumerate(parts):
            if p == "--reason" and i + 1 < len(parts):
                reason = " ".join(parts[i + 1:])
                break
        api_url = self.terminal.config.get("api_url", "http://localhost:8000")
        project_info = {"name": project_id}
        financials = {"deposit_amount": 0, "unpaid_invoices": 0,
                      "guaranteed_monthly": 0, "exit_penalty_months": 3,
                      "prepayment_received": 0, "renovation_cost": 0}
        try:
            import aiohttp
            async with aiohttp.ClientSession(trust_env=True) as sess:
                async with sess.get(
                    f"{api_url}/api/realty/contracts/{project_id}",
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as resp:
                    if resp.status == 200:
                        ctr = (await resp.json()).get("data", {})
                        from datetime import date
                        start = ctr.get("start_date", "")
                        used_months = 0
                        if start:
                            try:
                                from dateutil.relativedelta import relativedelta
                                d0 = date.fromisoformat(start)
                                delta = relativedelta(date.today(), d0)
                                used_months = delta.years * 12 + delta.months
                            except Exception:
                                pass
                        project_info.update({
                            "contract_years": ctr.get("contract_years", 1),
                            "used_months": used_months,
                            "contract_end": ctr.get("end_date", ""),
                        })
                        financials.update({
                            "deposit_amount": ctr.get("deposit_amount", 0),
                            "guaranteed_monthly": ctr.get("guaranteed_monthly", 0),
                            "exit_penalty_months": ctr.get("exit_penalty_months", 3),
                        })
                        contract_loaded = True
                        p(self.context, f"已加载合同规则: 保底 {ctr.get('guaranteed_monthly',0):,}元/月", "ok")
                async with sess.get(
                    f"{api_url}/api/realty/invoices?project_id={project_id}&status=unpaid",
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as resp2:
                    if resp2.status == 200:
                        body2 = await resp2.json()
                        summary = body2.get("data", {}).get("summary", {})
                        unpaid = summary.get("total_amount", 0) - summary.get("paid_amount", 0)
                        financials["unpaid_invoices"] = unpaid
                        if unpaid > 0:
                            p(self.context, f"发现未结账单合计: {unpaid:,.2f}元", "ok")
        except Exception:
            pass
        if not contract_loaded:
            self._realty_needs(project_id, "Usage: /exit-calc <project_id> [--reason …]")
            return
        await self._run_realty_agent("exit_settlement", project_id, {
            "project_info": project_info,
            "financials": financials,
            "asset_condition": {},
            "exit_reason": reason,
        })

    def _realty_needs(self, project_id: str | None, usage: str) -> bool:
        """Say what is missing and return True when a realty command has nothing to work on.

        These commands ran their agents on "demo_project", zeros or a made-up
        contract (30,000 a month, 10% share) when the Arthera realty backend
        had nothing, and the agent then gave a verdict: /ops-report called a
        project with no data "very high risk" with "member repurchase rate
        is low".
        """
        if project_id:
            msg = ui_text(self, f"没有找到 {project_id} 的数据：这项功能读取 Arthera 不动产后端里的项目数据，"
                                f"没有数据就不做分析。",
                          f"No data found for {project_id}: this reads project data from the Arthera realty "
                          f"backend and does not analyse without it.")
        else:
            msg = ui_text(self, "需要项目 ID。", "A project ID is needed.")
        from ._ui import print_error
        print_error(self.context, msg, usage)
        return True

    async def _run_realty_agent(self, agent_name: str, project_id: str, input_data: dict):
        if self.context.has_rich:
            with self.context.console.status(f"[dim]{ui_text(self, f'运行 {agent_name} Agent', f'Running the {agent_name} agent')}...[/dim]", spinner="dots"):
                result = await self._call_realty_agent(agent_name, project_id, input_data)
        else:
            print(f"Running {agent_name}...")
            result = await self._call_realty_agent(agent_name, project_id, input_data)
        if result:
            print_realty_result(self.context, result, agent_name)

    async def _run_realty_team(self, agents: list, project_id: str, input_data: dict):
        import asyncio
        if self.context.has_rich:
            _names = ', '.join(agents)
            with self.context.console.status(f"[dim]{ui_text(self, f'并行扫描 {_names}', f'Scanning {_names} in parallel')}...[/dim]", spinner="dots"):
                tasks = [self._call_realty_agent(n, project_id, input_data) for n in agents]
                results = await asyncio.gather(*tasks, return_exceptions=False)
        else:
            tasks = [self._call_realty_agent(n, project_id, input_data) for n in agents]
            results = await asyncio.gather(*tasks, return_exceptions=False)
        for res, name in zip(results, agents):
            if res:
                print_realty_result(self.context, res, name)

    async def _call_realty_agent(self, agent_name: str, project_id: str, input_data: dict):
        try:
            from agents.registry import get_registry
            cls = get_registry().get(agent_name)
            if not cls:
                p(self.context, f"Agent '{agent_name}' 未注册", "error")
                return None
            llm = None
            try:
                from providers.llm.registry import list_available_providers, get_provider
                avail = [p for p in list_available_providers() if p.get("available")]
                if avail:
                    llm = get_provider(avail[0]["name"])
            except Exception:
                pass
            agent = cls(llm_provider=llm)
            result = await agent.analyze(project_id, input_data)
            return result
        except Exception as e:
            p(self.context, f"Agent {agent_name} 执行失败: {e}", "error")
            return None
