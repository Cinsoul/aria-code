# 仓储 ERP Agents

仓储 Agents 是只读的运营风险分析器；它们不保存 ERP、WMS 或货代凭据，也不会修改库存、入库单或运输单。

## 可用 Agent

- `warehouse_logistics_sync`：读取 `connectors`，检查 `name`、`delay_minutes`、`failed_jobs`。
- `warehouse_inbound_exceptions`：读取 `inbounds`，检查 `id`、`expected_qty`、`received_qty`、`damaged_qty`、`overdue`。
- `warehouse_inventory_health`：读取 `skus` 与 `locations`，检查安全库存和库位利用率。

调用 `AgentTeam` 时请使用 `WAREHOUSE_TEAM` 与 `WAREHOUSE_SCHEME`，不要使用金融默认信号方案：

```python
from agents.team import AgentTeam
from agents.warehouse import WAREHOUSE_SCHEME, WAREHOUSE_TEAM

team = AgentTeam(signal_scheme=WAREHOUSE_SCHEME)
result = await team.run("WH-CN-01", agents=WAREHOUSE_TEAM, agent_data={...})
```

仓库包含一个最小只读 ERP 快照客户端。生产 ERP/WMS 应在上游完成认证、分页、重试、审计和字段校验，然后仅把上述最小只读数据契约传入 Agent。

## CLI 与 ERP 快照端点

配置 `ARIA_WAREHOUSE_ERP_URL` 与只读 `ARIA_WAREHOUSE_ERP_TOKEN` 后，可运行：

```text
/warehouse WH-CN-01
/warehouse WH-CN-01 --json
```

客户端只发出一个 `GET` 请求，默认端点为
`/api/v1/warehouses/{warehouse_id}/agent-snapshot`。响应可直接是对象，或包在
`data` 对象中；其中只会读取 `connectors`、`inbounds`、`skus`、`locations` 四个列表。
不会调用任何写入型 ERP API。

## 3PL 库存与承运商分析

面向第三方物流（3PL）客户的两个分析，直接读 CSV 或 JSON 文件，不需要连接 ERP。

```text
/inventory skus.csv --owner ACME
/carriers waybills.csv --owner ACME
```

**货主隔离。** 3PL 同时持有多个货主的数据，把它们混在一起算出的数字，等于把一个客户的商业数据交给另一个客户。所以三个物流分析（`/inventory`、`/carriers` 和原有的 `analyze_logistics_data`）都先经过同一道检查：

- 数据里没有 `owner_id`：当作单一货主数据，直接分析
- 数据只属于一个货主：直接分析
- 数据跨多个货主：**拒绝**，除非用 `--owner` 指定一个货主（结果可以给该客户看），或用 `--all-owners` 明确要求 3PL 内部的跨货主视图（结果首行标注"不可对客户分发"）
- 部分记录有 `owner_id`、部分没有：拒绝，因为无法归属

拒绝时的提示只说数据涉及几个货主，不会说出是哪几个。

**`/inventory`：补货与库存结构。** 每个 SKU 需要 `sku`、`on_hand`、`lead_time_days`，以及 `daily_demand`（每日需求序列，CSV 里用分号分隔）。可选 `on_order`、`backorder`、`lead_time_std_days`、`unit_cost`（ABC 需要）、`days_since_last_movement`。

```text
安全库存 = z · √(L·σ_d² + d̄²·σ_L²)
补货点   = d̄·L + 安全库存
补到水位 = 补货点 + d̄·R            R = 盘点周期（--review-days，默认 7）
建议数量 = 补到水位 − 库存位置     库存位置 ≤ 补货点时
```

需求历史少于 14 天的 SKU 不给补货点，只标注"历史不足"，因为基于几天数据算出的安全库存会给出错误但看似确定的结论。ABC 按货主内年消耗金额（80/95），XYZ 按需求变异系数（0.5/1.0）；呆滞 ≥ 90 天无动，慢动 ≥ 30 天。

**`/carriers`：承运商评分、运费异常与可节省金额。** 每张运单需要 `carrier`、`total_cost`，建议同时提供 `origin`、`destination`（按线路比较）、`billed_weight_kg`、`is_on_time`、`has_exception`。

- 同一线路内排名，依据是准时率的 95% Wilson 置信下界，而不是原始准时率：1/1 准时（下界 21%）不会排在 98/100 准时（下界 93%）前面。少于 20 单（`--min-shipments`）的承运商不参与排名。
- 运费异常用线路内每公斤成本的修正 z 分数（> 3.5）。合同运价线路上大多数运单价格相同，此时 MAD 为 0，会自动改用平均绝对偏差，避免恰好漏掉最容易看出的高收费。
- 只有当替代承运商**更便宜且同样可靠**（置信下界不低于现有承运商）时才给出节省建议；金额 = 运量 × 每公斤差价，不含合同条款、附加费、最低收费和运力限制。

每个结果都附带所用公式和阈值，可以逐项手工复核。
